"""
Admin handlers module.
Handles admin commands and management functions.
"""

from typing import List, Optional, Dict, Any
import logging
from datetime import datetime, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CommandHandler, CallbackQueryHandler
from telegram.constants import ParseMode

from database import db_manager
from models.user import UserRepository
from models.software import SoftwareRepository
from models.analytics import AnalyticsRepository
from services.file_service import file_service
from services.backup_service import backup_service
from services.notification_service import notification_service
from utils.helpers import (
    escape_markdown, format_file_size, format_datetime,
    truncate_text
)
from config import settings

logger = logging.getLogger(__name__)


class AdminHandlers:
    """Handlers for admin commands and management."""

    @staticmethod
    def is_admin(user_id: int) -> bool:
        """Check if user is admin."""
        return user_id in settings.admin_ids

    async def admin_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /admin command.
        Show admin dashboard.
        """
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            await update.message.reply_text(
                "⛔ *غير مصرح*\n"
                "هذا الأمر مخصص للمشرفين فقط.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        # Get dashboard stats
        async for session in db_manager.get_session():
            stats = await AnalyticsRepository.get_dashboard_stats(session)

        # Format dashboard message
        dashboard_text = (
            "📊 *لوحة التحكم*\n\n"
            "👥 *المستخدمين:*\n"
            f"• الإجمالي: {stats['users']['total']}\n"
            f"• النشطون اليوم: {stats['users']['active_today']}\n"
            f"• النشطون الشهر: {stats['users']['active_month']}\n\n"
            "📦 *البرامج:*\n"
            f"• الإجمالي: {stats['software']['total']}\n\n"
            "📈 *النشاط:*\n"
            f"• إجمالي البحث: {stats['activity']['total_searches']}\n"
            f"• بحث اليوم: {stats['activity']['searches_today']}\n"
            f"• إجمالي التحميل: {stats['activity']['total_downloads']}\n"
            f"• تحميل اليوم: {stats['activity']['downloads_today']}\n"
        )

        # Admin menu keyboard
        keyboard = [
            [
                InlineKeyboardButton(
                    "📋 إدارة البرامج",
                    callback_data="admin_software"
                ),
                InlineKeyboardButton(
                    "👥 إدارة المستخدمين",
                    callback_data="admin_users"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 إحصائيات",
                    callback_data="admin_stats"
                ),
                InlineKeyboardButton(
                    "📢 إرسال جماعي",
                    callback_data="admin_broadcast"
                ),
            ],
            [
                InlineKeyboardButton(
                    "💾 نسخ احتياطي",
                    callback_data="admin_backup"
                ),
                InlineKeyboardButton(
                    "🔧 صيانة",
                    callback_data="admin_maintenance"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔄 إعادة فهرسة",
                    callback_data="admin_reindex"
                ),
                InlineKeyboardButton(
                    "⚙️ الإعدادات",
                    callback_data="admin_settings"
                ),
            ],
        ]

        await update.message.reply_text(
            dashboard_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def add_software_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /addsoftware command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            await update.message.reply_text("⛔ غير مصرح")
            return

        if not update.message.reply_to_message:
            await update.message.reply_text(
                "📝 *لإضافة برنامج:*\n"
                "1. قم بالرد على ملف في القناة\n"
                "2. استخدم الأمر `/addsoftware`\n"
                "3. أضف وصفاً في الرد\n\n"
                "*مثال:*\n"
                "`/addsoftware Chrome متصفح ويب`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        # Get file from replied message
        replied_msg = update.message.reply_to_message
        if not replied_msg.document:
            await update.message.reply_text(
                "⚠️ يجب الرد على ملف لإضافته."
            )
            return

        # Parse command arguments
        args = context.args
        caption = " ".join(args) if args else replied_msg.caption or ""

        # Prepare message data
        message_data = {
            "message_id": replied_msg.message_id,
            "channel_id": settings.channel_id,
            "document": {
                "file_name": replied_msg.document.file_name,
                "file_size": replied_msg.document.file_size,
                "mime_type": replied_msg.document.mime_type,
            },
            "caption": caption,
        }

        # Index the file
        async for session in db_manager.get_session():
            result = await file_service.index_channel_message(
                session, message_data
            )

        if result:
            await update.message.reply_text(
                f"✅ *تمت إضافة البرنامج بنجاح*\n\n"
                f"📦 *الاسم:* {escape_markdown(result['name'])}\n"
                f"🆔 *المعرف:* `{result['id']}`\n"
                f"💾 *الحجم:* {escape_markdown(result['file_size_formatted'])}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                "❌ فشل في إضافة البرنامج. تحقق من السجلات."
            )

    async def delete_software_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /delsoftware command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        if not context.args:
            await update.message.reply_text(
                "📝 *استخدم:* `/delsoftware [id]`\n"
                "لحذف برنامج باستخدام معرفه.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        try:
            software_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ معرف غير صالح.")
            return

        async for session in db_manager.get_session():
            software = await SoftwareRepository.get_by_id(session, software_id)

            if not software:
                await update.message.reply_text("❌ البرنامج غير موجود.")
                return

            # Confirm deletion
            keyboard = [[
                InlineKeyboardButton(
                    "✅ نعم، احذف",
                    callback_data=f"confirm_delete_{software_id}"
                ),
                InlineKeyboardButton(
                    "❌ إلغاء",
                    callback_data="cancel_delete"
                ),
            ]]

            await update.message.reply_text(
                f"⚠️ *تأكيد الحذف*\n\n"
                f"هل أنت متأكد من حذف:\n"
                f"*{escape_markdown(software.name)}*\n\n"
                f"هذا الإجراء لا يمكن التراجع عنه.",
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    async def broadcast_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /broadcast command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        if not context.args:
            await update.message.reply_text(
                "📢 *لإرسال رسالة جماعية:*\n"
                "`/broadcast نص الرسالة`\n\n"
                "سيتم إرسالها لجميع المستخدمين.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        message_text = " ".join(context.args)

        # Send broadcast
        async for session in db_manager.get_session():
            results = await notification_service.send_broadcast(
                session=session,
                admin_id=user_id,
                message_text=escape_markdown(message_text),
            )

        await update.message.reply_text(
            f"📢 *نتائج الإرسال*\n\n"
            f"✅ تم الإرسال: {results['successful']}\n"
            f"❌ فشل: {results['failed']}\n"
            f"🚫 محظور: {results['blocked']}\n"
            f"📊 الإجمالي: {results['total_users']}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def stats_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /stats command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        async for session in db_manager.get_session():
            # Get various stats
            dashboard = await AnalyticsRepository.get_dashboard_stats(session)
            most_searched = await AnalyticsRepository.get_most_searched(session, 5)
            most_downloaded = await AnalyticsRepository.get_most_downloaded(session, 5)
            search_trends = await AnalyticsRepository.get_search_trends(session, 7)

        stats_text = (
            "📊 *إحصائيات تفصيلية*\n\n"
            f"👥 المستخدمين: {dashboard['users']['total']}\n"
            f"📦 البرامج: {dashboard['software']['total']}\n"
            f"🔍 عمليات البحث: {dashboard['activity']['total_searches']}\n"
            f"📥 التحميلات: {dashboard['activity']['total_downloads']}\n\n"
        )

        # Most searched
        stats_text += "*🔍 الأكثر بحثاً:*\n"
        for item in most_searched[:5]:
            stats_text += f"• {escape_markdown(item['name'])} ({item['search_count']})\n"

        # Most downloaded
        stats_text += "\n*📥 الأكثر تحميلاً:*\n"
        for item in most_downloaded[:5]:
            stats_text += f"• {escape_markdown(item['name'])} ({item['download_count']})\n"

        await update.message.reply_text(
            stats_text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def backup_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /backup command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        async for session in db_manager.get_session():
            result = await backup_service.create_backup(session)

        if result:
            await update.message.reply_text(
                f"✅ *تم إنشاء نسخة احتياطية*\n\n"
                f"📁 الملف: `{result['name']}.zip`\n"
                f"💾 الحجم: {format_file_size(result['size'] / (1024*1024))}\n"
                f"📅 التاريخ: {result['timestamp']}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text("❌ فشل إنشاء النسخة الاحتياطية.")

    async def restore_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /restore command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        # List available backups
        backups = await backup_service.list_backups()

        if not backups:
            await update.message.reply_text("❌ لا توجد نسخ احتياطية.")
            return

        message_text = "💾 *النسخ الاحتياطية المتاحة:*\n\n"
        keyboard = []

        for backup in backups[:10]:
            message_text += (
                f"📁 {escape_markdown(backup['name'])}\n"
                f"   📅 {backup['created_at']}\n"
                f"   💾 {format_file_size(backup['size'] / (1024*1024))}\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"استعادة {backup['name'][:20]}",
                    callback_data=f"restore_{backup['name']}"
                )
            ])

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def reindex_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /reindex command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        await update.message.reply_text("🔄 *جاري إعادة الفهرسة...*")

        async for session in db_manager.get_session():
            count = await file_service.reindex_all(session)

        await update.message.reply_text(
            f"✅ *تمت إعادة الفهرسة بنجاح*\n"
            f"📊 عدد البرامج المفهرسة: {count}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def maintenance_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /maintenance command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        # Toggle maintenance mode
        from config import settings as app_settings
        
        if settings.maintenance_mode:
            # Turn off
            settings.maintenance_mode = False
            status = "معطل"
        else:
            # Turn on
            settings.maintenance_mode = True
            status = "مفعل"

        await update.message.reply_text(
            f"🔧 *وضع الصيانة:* {status}",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def block_user_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /block command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        if not context.args:
            await update.message.reply_text(
                "📝 *استخدم:* `/block [user_id]`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ معرف غير صالح.")
            return

        async for session in db_manager.get_session():
            await UserRepository.block_user(session, target_id)

        await update.message.reply_text(
            f"🚫 *تم حظر المستخدم:* `{target_id}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def unblock_user_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /unblock command."""
        user_id = update.effective_user.id

        if not self.is_admin(user_id):
            return

        if not context.args:
            await update.message.reply_text(
                "📝 *استخدم:* `/unblock [user_id]`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        try:
            target_id = int(context.args[0])
        except ValueError:
            await update.message.reply_text("⚠️ معرف غير صالح.")
            return

        async for session in db_manager.get_session():
            await UserRepository.unblock_user(session, target_id)

        await update.message.reply_text(
            f"✅ *تم فك حظر المستخدم:* `{target_id}`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    def get_handlers(self) -> List:
        """Get all admin handlers."""
        return [
            CommandHandler("admin", self.admin_command),
            CommandHandler("addsoftware", self.add_software_command),
            CommandHandler("delsoftware", self.delete_software_command),
            CommandHandler("broadcast", self.broadcast_command),
            CommandHandler("stats", self.stats_command),
            CommandHandler("backup", self.backup_command),
            CommandHandler("restore", self.restore_command),
            CommandHandler("reindex", self.reindex_command),
            CommandHandler("maintenance", self.maintenance_command),
            CommandHandler("block", self.block_user_command),
            CommandHandler("unblock", self.unblock_user_command),
        ]


# Global instance
admin_handlers = AdminHandlers()
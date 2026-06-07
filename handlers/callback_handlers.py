"""
Callback handlers module.
Handles all inline button callbacks.
"""

from typing import Optional, Dict, Any
import logging
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, CallbackQueryHandler
from telegram.constants import ParseMode

from database import db_manager
from models.user import UserRepository
from models.software import SoftwareRepository
from services.search_service import search_service
from services.file_service import file_service
from services.backup_service import backup_service
from utils.helpers import (
    format_file_size, escape_markdown, truncate_text,
    get_relative_time, calculate_rating_stats,
)
from config import settings

logger = logging.getLogger(__name__)


class CallbackHandlers:
    """Handlers for callback queries from inline buttons."""

    @staticmethod
    async def handle_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Main callback handler.
        Routes callbacks to appropriate handlers.
        """
        query = update.callback_query
        await query.answer()

        user_id = update.effective_user.id
        data = query.data

        if not data:
            return

        try:
            # Route callbacks
            if data.startswith("download_"):
                await self._handle_download(update, context)

            elif data.startswith("info_"):
                await self._handle_info(update, context)

            elif data.startswith("rate_"):
                await self._handle_rate(update, context)

            elif data.startswith("fav_"):
                await self._handle_favorite(update, context)

            elif data.startswith("unfav_"):
                await self._handle_unfavorite(update, context)

            elif data.startswith("share_"):
                await self._handle_share(update, context)

            elif data.startswith("similar_"):
                await self._handle_similar(update, context)

            elif data.startswith("page_"):
                await self._handle_pagination(update, context)

            elif data.startswith("sort_"):
                await self._handle_sort(update, context)

            elif data.startswith("category_"):
                await self._handle_category(update, context)

            elif data == "categories":
                await self._show_categories(update, context)

            elif data == "popular":
                await self._show_popular(update, context)

            elif data.startswith("confirm_delete_"):
                await self._handle_delete_confirm(update, context)

            elif data == "cancel_delete":
                await self._handle_delete_cancel(update, context)

            elif data.startswith("restore_"):
                await self._handle_restore(update, context)

            elif data.startswith("setting_"):
                await self._handle_settings(update, context)

            elif data.startswith("admin_"):
                await self._handle_admin_callback(update, context)

            elif data.startswith("rating_"):
                await self._handle_rating_submit(update, context)

            else:
                logger.warning(f"Unknown callback: {data}")

        except Exception as e:
            logger.error(f"Callback error: {e}", exc_info=True)
            await query.edit_message_text(
                "❌ حدث خطأ. يرجى المحاولة مرة أخرى."
            )

    async def _handle_download(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle download button."""
        query = update.callback_query
        user_id = update.effective_user.id

        # Extract software ID
        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            # Get software info
            software = await SoftwareRepository.get_by_id(session, software_id)

            if not software:
                await query.edit_message_text(
                    "❌ البرنامج غير متوفر حالياً."
                )
                return

            # Process download
            download_info = await file_service.download_software(
                session, software_id, user_id
            )

            if not download_info:
                await query.edit_message_text(
                    "❌ فشل في تحميل البرنامج."
                )
                return

            # Forward message from channel
            try:
                await context.bot.forward_message(
                    chat_id=user_id,
                    from_chat_id=software.channel_id,
                    message_id=software.message_id,
                )

                # Update message with success
                await query.edit_message_text(
                    f"✅ *تم إرسال الملف*\n\n"
                    f"📦 {escape_markdown(software.name)}\n"
                    f"💾 {format_file_size(software.file_size or 0)}\n\n"
                    f"تحقق من المحادثة لاستلام الملف 📨",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

            except Exception as e:
                logger.error(f"Forward error: {e}")
                await query.edit_message_text(
                    f"⚠️ *تعذر إرسال الملف*\n\n"
                    f"قد تحتاج للانضمام إلى القناة أولاً:\n"
                    f"{escape_markdown(software.channel_id)}",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )

    async def _handle_info(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle info button."""
        query = update.callback_query

        # Extract software ID
        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            software = await SoftwareRepository.get_by_id(session, software_id)

            if not software:
                await query.edit_message_text(
                    "❌ البرنامج غير موجود."
                )
                return

            # Get user rating if exists
            user_id = update.effective_user.id
            user_rating = await UserRepository.get_user_rating(
                session, user_id, software_id
            )

            # Build info message
            avg_rating = 0
            if software.rating_count > 0:
                avg_rating = round(
                    software.rating_sum / software.rating_count, 1
                )

            stars = "⭐" * int(avg_rating) + "☆" * (5 - int(avg_rating))

            info_text = (
                f"📋 *معلومات البرنامج*\n\n"
                f"📦 *الاسم:* {escape_markdown(software.name)}\n"
                f"📝 *الوصف:* {escape_markdown(software.description or 'لا يوجد وصف')}\n"
                f"🔢 *الإصدار:* {escape_markdown(software.version or 'غير محدد')}\n"
                f"📁 *النوع:* {escape_markdown(software.file_type or 'غير محدد')}\n"
                f"💾 *الحجم:* {escape_markdown(format_file_size(software.file_size or 0))}\n"
                f"📂 *الفئة:* {escape_markdown(software.category or 'غير مصنف')}\n"
                f"📅 *تاريخ الإضافة:* {escape_markdown(str(software.added_date.strftime('%Y-%m-%d') if software.added_date else 'غير معروف'))}\n"
                f"📥 *التحميلات:* {software.download_count}\n"
                f"🔍 *مرات البحث:* {software.search_count}\n\n"
                f"*التقييم:* {stars} ({avg_rating}/5)\n"
                f"عدد المقيمين: {software.rating_count}\n"
            )

            if user_rating:
                info_text += (
                    f"\n*تقييمك:* {'⭐' * user_rating['rating']}\n"
                )

            # Action buttons
            keyboard = [
                [
                    InlineKeyboardButton(
                        "📥 تحميل",
                        callback_data=f"download_{software_id}"
                    ),
                    InlineKeyboardButton(
                        "⭐ تقييم",
                        callback_data=f"rate_{software_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "❤️ إضافة للمفضلة",
                        callback_data=f"fav_{software_id}"
                    ),
                    InlineKeyboardButton(
                        "📤 مشاركة",
                        callback_data=f"share_{software_id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔄 برامج مشابهة",
                        callback_data=f"similar_{software_id}"
                    ),
                    InlineKeyboardButton(
                        "🔙 رجوع",
                        callback_data="popular"
                    ),
                ],
            ]

            await query.edit_message_text(
                info_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard),
                disable_web_page_preview=True,
            )

    async def _handle_rate(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle rate button - show rating options."""
        query = update.callback_query

        software_id = int(query.data.split("_")[1])

        # Rating stars keyboard
        keyboard = []
        for i in range(1, 6):
            stars = "⭐" * i + "☆" * (5 - i)
            keyboard.append([
                InlineKeyboardButton(
                    stars,
                    callback_data=f"rating_{software_id}_{i}"
                )
            ])

        keyboard.append([
            InlineKeyboardButton(
                "🔙 رجوع",
                callback_data=f"info_{software_id}"
            )
        ])

        await query.edit_message_text(
            "⭐ *قيم البرنامج*\n\n"
            "اختر تقييمك من 1 إلى 5 نجوم:",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_rating_submit(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle rating submission."""
        query = update.callback_query
        user_id = update.effective_user.id

        # Parse rating data
        parts = query.data.split("_")
        software_id = int(parts[1])
        rating = int(parts[2])

        async for session in db_manager.get_session():
            # Submit rating
            success = await UserRepository.rate_software(
                session=session,
                user_id=user_id,
                software_id=software_id,
                rating=rating,
            )

            if success:
                software = await SoftwareRepository.get_by_id(
                    session, software_id
                )

                avg_rating = 0
                if software and software.rating_count > 0:
                    avg_rating = round(
                        software.rating_sum / software.rating_count, 1
                    )

                await query.edit_message_text(
                    f"✅ *تم التقييم بنجاح*\n\n"
                    f"تقييمك: {'⭐' * rating}\n"
                    f"متوسط التقييم: {avg_rating}/5 ⭐\n"
                    f"عدد المقيمين: {software.rating_count if software else 0}",
                    parse_mode=ParseMode.MARKDOWN_V2,
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "📋 معلومات البرنامج",
                            callback_data=f"info_{software_id}"
                        )
                    ]]),
                )
            else:
                await query.edit_message_text(
                    "❌ فشل في إضافة التقييم."
                )

    async def _handle_favorite(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle add to favorites."""
        query = update.callback_query
        user_id = update.effective_user.id

        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            success = await UserRepository.add_favorite(
                session, user_id, software_id
            )

            if success:
                await query.answer("✅ تمت الإضافة إلى المفضلة")
            else:
                await query.answer("ℹ️ موجود بالفعل في المفضلة")

            # Update button
            keyboard = query.message.reply_markup.inline_keyboard
            for row in keyboard:
                for button in row:
                    if button.callback_data == f"fav_{software_id}":
                        button.text = "❤️ تمت الإضافة"
                        button.callback_data = f"unfav_{software_id}"

            await query.edit_message_reply_markup(
                InlineKeyboardMarkup(keyboard)
            )

    async def _handle_unfavorite(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle remove from favorites."""
        query = update.callback_query
        user_id = update.effective_user.id

        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            await UserRepository.remove_favorite(
                session, user_id, software_id
            )

        await query.answer("❌ تمت الإزالة من المفضلة")

        # Update button
        keyboard = query.message.reply_markup.inline_keyboard
        for row in keyboard:
            for button in row:
                if button.callback_data == f"unfav_{software_id}":
                    button.text = "❤️ إضافة للمفضلة"
                    button.callback_data = f"fav_{software_id}"

        await query.edit_message_reply_markup(
            InlineKeyboardMarkup(keyboard)
        )

    async def _handle_share(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle share button."""
        query = update.callback_query

        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            software = await SoftwareRepository.get_by_id(session, software_id)

            if not software:
                await query.answer("❌ البرنامج غير موجود")
                return

            # Create share message
            share_text = (
                f"📦 *{escape_markdown(software.name)}*\n"
                f"🔢 الإصدار: {escape_markdown(software.version or 'غير محدد')}\n"
                f"💾 الحجم: {format_file_size(software.file_size or 0)}\n\n"
                f"لتحميل البرنامج، ابحث عنه في البوت:\n"
                f"@{context.bot.username}"
            )

            await query.answer(
                "📤 يمكنك مشاركة هذا البرنامج مع أصدقائك"
            )

            # Send share message as new message
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=share_text,
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _handle_similar(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle similar software button."""
        query = update.callback_query

        software_id = int(query.data.split("_")[1])

        async for session in db_manager.get_session():
            related = await file_service.get_related_software(
                session, software_id, limit=5
            )

            if not related:
                await query.edit_message_text(
                    "❌ لا توجد برامج مشابهة."
                )
                return

            message_text = "🔄 *برامج مشابهة*\n\n"
            keyboard = []

            for sw in related:
                message_text += (
                    f"📦 {escape_markdown(sw['name'])}\n"
                    f"💾 {sw['file_size_formatted']}\n\n"
                )
                keyboard.append([
                    InlineKeyboardButton(
                        f"📥 {sw['name'][:30]}",
                        callback_data=f"download_{sw['id']}"
                    ),
                    InlineKeyboardButton(
                        "📋",
                        callback_data=f"info_{sw['id']}"
                    ),
                ])

            keyboard.append([
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data=f"info_{software_id}"
                )
            ])

            await query.edit_message_text(
                message_text,
                parse_mode=ParseMode.MARKDOWN_V2,
                reply_markup=InlineKeyboardMarkup(keyboard),
            )

    async def _handle_pagination(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle search result pagination."""
        query = update.callback_query

        # Parse pagination data
        parts = query.data.split("_", 2)
        search_query = parts[1]
        page = int(parts[2])

        user_id = update.effective_user.id

        async for session in db_manager.get_session():
            results = await search_service.search(
                session=session,
                query=search_query,
                user_id=user_id,
                limit=10,
                offset=page * 10,
            )

        # Display results for this page
        from handlers.user_handlers import UserHandlers
        user_handler = UserHandlers()

        # We need to edit the message, not send new one
        # Build results text
        items_per_page = 5
        total_pages = max(1, (results["total_count"] + items_per_page - 1) // items_per_page)
        
        start_idx = 0  # Results are already offset
        page_results = results["results"][:items_per_page]

        message_text = f"🔍 *نتائج البحث عن:* `{escape_markdown(search_query)}`\n"
        message_text += f"📊 *عدد النتائج:* {results['total_count']}\n"
        message_text += f"📄 *صفحة:* {page + 1}/{total_pages}\n\n"

        keyboard = []
        for i, software in enumerate(page_results):
            desc = truncate_text(software.get("description", ""), 80)
            rating = software.get("rating", 0)
            stars = "⭐" * int(rating) + "☆" * (5 - int(rating))

            message_text += (
                f"*{i + 1}\.* {escape_markdown(software['name'])}\n"
                f"📦 {escape_markdown(software.get('version', 'N/A'))} | "
                f"💾 {escape_markdown(format_file_size(software.get('file_size', 0)))}\n"
                f"{stars} | 📥 {software.get('download_count', 0)}\n"
                f"_{escape_markdown(desc)}_\n\n"
            )

            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {software['name'][:25]}",
                    callback_data=f"download_{software['id']}"
                ),
                InlineKeyboardButton(
                    "📋",
                    callback_data=f"info_{software['id']}"
                ),
                InlineKeyboardButton(
                    "⭐",
                    callback_data=f"rate_{software['id']}"
                ),
            ])

        # Navigation buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ السابق",
                    callback_data=f"page_{search_query}_{page - 1}"
                )
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    "التالي ➡️",
                    callback_data=f"page_{search_query}_{page + 1}"
                )
            )
        if nav_buttons:
            keyboard.append(nav_buttons)

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def _handle_sort(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle sort buttons."""
        query = update.callback_query

        parts = query.data.split("_", 2)
        sort_type = parts[1]
        search_query = parts[2]

        user_id = update.effective_user.id

        async for session in db_manager.get_session():
            results = await search_service.search(
                session=session,
                query=search_query,
                user_id=user_id,
                limit=10,
                sort_by=sort_type,
            )

        # Display sorted results (similar to _handle_pagination)
        message_text = f"🔍 *نتائج البحث عن:* `{escape_markdown(search_query)}`\n"
        message_text += f"📊 *ترتيب حسب:* {sort_type}\n"
        message_text += f"📊 *عدد النتائج:* {results['total_count']}\n\n"

        keyboard = []
        for i, software in enumerate(results["results"][:5]):
            message_text += (
                f"*{i + 1}\.* {escape_markdown(software['name'])}\n"
                f"📥 {software.get('download_count', 0)} | "
                f"⭐ {software.get('rating', 0)}\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {software['name'][:25]}",
                    callback_data=f"download_{software['id']}"
                ),
                InlineKeyboardButton(
                    "📋",
                    callback_data=f"info_{software['id']}"
                ),
            ])

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def _handle_category(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle category selection."""
        query = update.callback_query

        category = query.data.split("_", 1)[1]

        async for session in db_manager.get_session():
            results, total = await SoftwareRepository.search_software(
                session=session,
                query="",
                category=category,
                limit=10,
            )

        if not results:
            await query.edit_message_text(
                f"❌ لا توجد برامج في فئة: {escape_markdown(category)}",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        message_text = f"📂 *فئة:* {escape_markdown(category)}\n"
        message_text += f"📊 *عدد البرامج:* {total}\n\n"

        keyboard = []
        for sw in results[:10]:
            message_text += (
                f"📦 {escape_markdown(sw.name)}\n"
                f"💾 {format_file_size(sw.file_size or 0)}\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {sw.name[:30]}",
                    callback_data=f"download_{sw.id}"
                ),
                InlineKeyboardButton(
                    "📋",
                    callback_data=f"info_{sw.id}"
                ),
            ])

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _show_categories(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show categories list."""
        query = update.callback_query

        async for session in db_manager.get_session():
            categories = await file_service.get_categories(session)

        message_text = "📂 *الفئات المتاحة*\n\n"
        keyboard = []

        for category in categories:
            message_text += f"• {escape_markdown(category)}\n"
            keyboard.append([
                InlineKeyboardButton(
                    category,
                    callback_data=f"category_{category}"
                )
            ])

        # Arrange in rows of 2
        keyboard_rows = [
            keyboard[i:i + 2] for i in range(0, len(keyboard), 2)
        ]

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
        )

    async def _show_popular(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show popular software."""
        query = update.callback_query

        async for session in db_manager.get_session():
            trending = await search_service.get_trending(session, limit=10)

        message_text = "🔥 *البرامج الشائعة*\n\n"
        keyboard = []

        for sw in trending:
            message_text += f"📦 {escape_markdown(sw['name'])}\n"
            message_text += f"📥 {sw['download_count']} تحميل\n\n"
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {sw['name'][:30]}",
                    callback_data=f"download_{sw['id']}"
                ),
                InlineKeyboardButton(
                    "📋",
                    callback_data=f"info_{sw['id']}"
                ),
            ])

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _handle_delete_confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle delete confirmation."""
        query = update.callback_query

        software_id = int(query.data.split("_")[2])

        async for session in db_manager.get_session():
            await file_service.delete_software(session, software_id)

        await query.edit_message_text(
            "✅ *تم حذف البرنامج بنجاح*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _handle_delete_cancel(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle delete cancellation."""
        query = update.callback_query

        await query.edit_message_text(
            "❌ *تم إلغاء الحذف*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    async def _handle_restore(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle backup restore."""
        query = update.callback_query

        backup_name = query.data.split("_", 1)[1]

        await query.edit_message_text(
            f"🔄 *جاري استعادة النسخة الاحتياطية...*\n"
            f"قد يستغرق هذا بعض الوقت.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        async for session in db_manager.get_session():
            success = await backup_service.restore_backup(
                session, backup_name
            )

        if success:
            await query.edit_message_text(
                "✅ *تمت استعادة النسخة الاحتياطية بنجاح*",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await query.edit_message_text(
                "❌ فشل في استعادة النسخة الاحتياطية.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _handle_settings(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle settings callbacks."""
        query = update.callback_query
        setting_type = query.data.split("_", 1)[1]

        if setting_type == "notifications":
            await query.answer("🔔 الإشعارات قيد التطوير")
        elif setting_type == "language":
            await query.edit_message_text(
                "🌐 *اختر اللغة:*\n\n"
                "• العربية (الحالية)\n"
                "• English\n\n"
                "_قريباً_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        elif setting_type == "stats":
            user_id = update.effective_user.id

            async for session in db_manager.get_session():
                stats = await UserRepository.get_user_stats(
                    session, user_id
                )

            await query.edit_message_text(
                f"📊 *إحصائياتك*\n\n"
                f"🔍 عمليات البحث: {stats['searches']}\n"
                f"📥 التحميلات: {stats['downloads']}\n"
                f"⭐ المفضلة: {stats['favorites']}\n",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        elif setting_type == "clear_history":
            await query.edit_message_text(
                "🗑️ *تم مسح السجل*\n\n"
                "_قريباً_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _handle_admin_callback(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle admin menu callbacks."""
        query = update.callback_query
        action = query.data.split("_", 1)[1]

        if action == "software":
            await self._admin_software_menu(update, context)
        elif action == "users":
            await self._admin_users_menu(update, context)
        elif action == "stats":
            await self._admin_stats(update, context)
        elif action == "broadcast":
            await self._admin_broadcast_prompt(update, context)
        elif action == "backup":
            await self._admin_backup_menu(update, context)
        elif action == "maintenance":
            await self._admin_maintenance_toggle(update, context)
        elif action == "reindex":
            await self._admin_reindex(update, context)
        elif action == "settings":
            await query.edit_message_text(
                "⚙️ *إعدادات المشرف*\n\n_قريباً_",
                parse_mode=ParseMode.MARKDOWN_V2,
            )

    async def _admin_software_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show admin software management menu."""
        query = update.callback_query

        async for session in db_manager.get_session():
            total = (await AnalyticsRepository.get_dashboard_stats(session))['software']['total']

        message_text = (
            f"📋 *إدارة البرامج*\n\n"
            f"📦 إجمالي البرامج: {total}\n\n"
            f"*الأوامر المتاحة:*\n"
            f"/addsoftware - إضافة برنامج\n"
            f"/delsoftware - حذف برنامج\n"
            f"/reindex - إعادة فهرسة\n"
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 رجوع للوحة التحكم",
                callback_data="admin_main"
            ),
        ]]

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _admin_users_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show admin users management menu."""
        query = update.callback_query

        async for session in db_manager.get_session():
            total = (await AnalyticsRepository.get_dashboard_stats(session))['users']['total']

        message_text = (
            f"👥 *إدارة المستخدمين*\n\n"
            f"👤 إجمالي المستخدمين: {total}\n\n"
            f"*الأوامر المتاحة:*\n"
            f"/block [id] - حظر مستخدم\n"
            f"/unblock [id] - فك الحظر\n"
            f"/stats - إحصائيات المستخدمين\n"
        )

        keyboard = [[
            InlineKeyboardButton(
                "🔙 رجوع",
                callback_data="admin_main"
            ),
        ]]

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _admin_stats(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show detailed admin statistics."""
        query = update.callback_query

        async for session in db_manager.get_session():
            stats = await AnalyticsRepository.get_dashboard_stats(session)
            top_downloaded = await AnalyticsRepository.get_most_downloaded(session, 5)
            top_searched = await AnalyticsRepository.get_most_searched(session, 5)

        message_text = "📊 *إحصائيات تفصيلية*\n\n"
        message_text += f"👥 المستخدمين: {stats['users']['total']}\n"
        message_text += f"📦 البرامج: {stats['software']['total']}\n"
        message_text += f"🔍 البحث: {stats['activity']['total_searches']}\n"
        message_text += f"📥 التحميل: {stats['activity']['total_downloads']}\n\n"

        message_text += "*الأكثر تحميلاً:*\n"
        for item in top_downloaded[:3]:
            message_text += f"• {escape_markdown(item['name'])} ({item['download_count']})\n"

        keyboard = [[
            InlineKeyboardButton("🔙 رجوع", callback_data="admin_main"),
        ]]

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _admin_broadcast_prompt(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show broadcast prompt."""
        query = update.callback_query

        await query.edit_message_text(
            "📢 *إرسال رسالة جماعية*\n\n"
            "استخدم الأمر:\n"
            "`/broadcast نص الرسالة`\n\n"
            "لإرسال رسالة لجميع المستخدمين.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_main"),
            ]]),
        )

    async def _admin_backup_menu(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Show backup management menu."""
        query = update.callback_query

        backups = await backup_service.list_backups()

        message_text = "💾 *إدارة النسخ الاحتياطي*\n\n"
        message_text += "*الأوامر المتاحة:*\n"
        message_text += "/backup - إنشاء نسخة جديدة\n"
        message_text += "/restore - استعادة نسخة\n\n"

        if backups:
            message_text += "*النسخ المتاحة:*\n"
            for backup in backups[:5]:
                message_text += f"📁 {backup['name']}\n"

        keyboard = [
            [
                InlineKeyboardButton(
                    "إنشاء نسخة",
                    callback_data="admin_backup_create"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🔙 رجوع",
                    callback_data="admin_main"
                ),
            ],
        ]

        await query.edit_message_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def _admin_maintenance_toggle(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Toggle maintenance mode."""
        query = update.callback_query

        settings.maintenance_mode = not settings.maintenance_mode
        status = "مفعل ✅" if settings.maintenance_mode else "معطل ❌"

        await query.edit_message_text(
            f"🔧 *وضع الصيانة:* {status}\n\n"
            "استخدم /maintenance للتبديل.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_main"),
            ]]),
        )

    async def _admin_reindex(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Trigger reindex."""
        query = update.callback_query

        await query.edit_message_text(
            "🔄 *جاري إعادة الفهرسة...*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        async for session in db_manager.get_session():
            count = await file_service.reindex_all(session)

        await query.edit_message_text(
            f"✅ *تمت إعادة الفهرسة*\n"
            f"📊 تم تحديث {count} برنامج.",
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("🔙 رجوع", callback_data="admin_main"),
            ]]),
        )

    def get_handlers(self) -> List:
        """Get all callback handlers."""
        return [
            CallbackQueryHandler(
                self.handle_callback,
                pattern="^.*$"
            ),
        ]


# Global instance
callback_handlers = CallbackHandlers()
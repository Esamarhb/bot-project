"""
User handlers module.
Handles all user-facing commands and interactions.
"""

from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    ContextTypes, CommandHandler, MessageHandler,
    filters, ConversationHandler
)
from telegram.constants import ParseMode

from database import db_manager
from models.user import UserRepository
from models.software import SoftwareRepository
from services.search_service import search_service
from services.file_service import file_service
from utils.helpers import (
    format_file_size, escape_markdown, truncate_text,
    get_relative_time, sanitize_input
)
from utils.security import security_manager
from utils.cache import cache_manager
from config import settings

logger = logging.getLogger(__name__)

# Conversation states
SEARCHING, VIEWING, RATING, REVIEWING = range(4)


class UserHandlers:
    """Handlers for user commands and messages."""

    def __init__(self):
        """Initialize user handlers."""
        self.search_service = search_service
        self.file_service = file_service

    async def start_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle /start command.
        Welcome message and user registration.
        """
        user = update.effective_user
        if not user:
            return

        # Security check
        is_allowed, reason = await security_manager.check_request(user.id)
        if not is_allowed:
            await update.message.reply_text(
                "⚠️ يرجى الانتظار قليلاً قبل المحاولة مرة أخرى."
            )
            return

        # Register/get user
        async for session in db_manager.get_session():
            db_user = await UserRepository.get_or_create_user(
                session=session,
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code or "ar",
            )

        # Welcome message
        welcome_text = (
            f"👋 *مرحباً {escape_markdown(user.first_name or 'مستخدم')}*\n\n"
            f"أنا بوت مكتبة البرامج الرقمية 📚\n\n"
            f"🔍 *للبحث عن برنامج:*\n"
            f"\- أرسل اسم البرنامج مباشرة\n"
            f"\- أو استخدم الأمر /search\n\n"
            f"📋 *الأوامر المتاحة:*\n"
            f"/start \- البدء\n"
            f"/search \- بحث متقدم\n"
            f"/popular \- البرامج الشائعة\n"
            f"/trending \- الأكثر تحميلاً\n"
            f"/categories \- الفئات\n"
            f"/favorites \- المفضلة\n"
            f"/history \- سجل التحميلات\n"
            f"/settings \- الإعدادات\n"
            f"/help \- المساعدة\n\n"
            f"💡 *مثال:* أرسل \'Chrome\' للبحث عن متصفح Chrome"
        )

        # Create keyboard
        keyboard = [
            ["🔍 بحث", "🔥 الشائعة"],
            ["⭐ المفضلة", "📂 الفئات"],
            ["📊 الأكثر تحميلاً", "⚙️ الإعدادات"],
        ]
        reply_markup = ReplyKeyboardMarkup(
            keyboard, resize_keyboard=True
        )

        await update.message.reply_text(
            welcome_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

    async def help_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /help command."""
        help_text = (
            "📖 *دليل المستخدم*\n\n"
            "🔍 *البحث عن البرامج:*\n"
            "• أرسل اسم البرنامج للبحث\n"
            "• استخدم /search للبحث المتقدم\n"
            "• يمكنك البحث بالاسم أو الوصف\n\n"
            "📋 *الأوامر الأساسية:*\n"
            "/start \- الصفحة الرئيسية\n"
            "/popular \- البرامج الشائعة\n"
            "/trending \- الأكثر تحميلاً\n"
            "/categories \- تصفح الفئات\n"
            "/favorites \- برامجي المفضلة\n"
            "/history \- سجل التحميلات\n"
            "/settings \- الإعدادات الشخصية\n\n"
            "⭐ *التقييم:*\n"
            "• قيم البرامج من 1 إلى 5 نجوم\n"
            "• اكتب مراجعتك للبرنامج\n\n"
            "💾 *التحميل:*\n"
            "• اضغط زر تحميل للحصول على البرنامج\n"
            "• يتم إعادة توجيه الملف من القناة\n\n"
            "📞 *للتواصل مع المشرف:* /contact"
        )

        await update.message.reply_text(
            help_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            disable_web_page_preview=True,
        )

    async def handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """
        Handle user text messages.
        Main search functionality.
        """
        user = update.effective_user
        text = update.message.text.strip()

        if not user or not text:
            return

        # Security check
        is_allowed, reason = await security_manager.check_request(user.id)
        if not is_allowed:
            if reason == "rate_limit_exceeded":
                await update.message.reply_text(
                    "⚠️ *تم تجاوز الحد المسموح*\n"
                    "يرجى الانتظار قليلاً قبل المحاولة مرة أخرى.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            return

        # Handle keyboard shortcuts
        if text == "🔍 بحث":
            await update.message.reply_text(
                "📝 *أرسل اسم البرنامج الذي تبحث عنه:*",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        elif text == "🔥 الشائعة":
            await self.popular_command(update, context)
            return
        elif text == "⭐ المفضلة":
            await self.favorites_command(update, context)
            return
        elif text == "📂 الفئات":
            await self.categories_command(update, context)
            return
        elif text == "📊 الأكثر تحميلاً":
            await self.trending_command(update, context)
            return
        elif text == "⚙️ الإعدادات":
            await self.settings_command(update, context)
            return

        # Sanitize input
        sanitized_text = security_manager.sanitize_input(text, 200)
        if not sanitized_text:
            await update.message.reply_text(
                "⚠️ نص البحث غير صالح."
            )
            return

        # Perform search
        await self._perform_search(
            update, context, sanitized_text, user.id
        )

    async def search_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /search command."""
        if not context.args:
            await update.message.reply_text(
                "📝 *استخدم الأمر كالتالي:*\n"
                "`/search اسم البرنامج`\n\n"
                "مثال: `/search Chrome`",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return

        query = " ".join(context.args)
        sanitized_query = security_manager.sanitize_input(query, 200)

        if sanitized_query:
            await self._perform_search(
                update, context, sanitized_query, update.effective_user.id
            )

    async def _perform_search(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        query: str,
        user_id: int,
    ) -> None:
        """
        Perform search and display results.

        Args:
            update: Telegram update
            context: Callback context
            query: Search query
            user_id: User ID
        """
        # Send searching message
        searching_msg = await update.message.reply_text(
            "🔍 *جاري البحث...*",
            parse_mode=ParseMode.MARKDOWN_V2,
        )

        async for session in db_manager.get_session():
            # Perform search
            results = await self.search_service.search(
                session=session,
                query=query,
                user_id=user_id,
                limit=10,
            )

            # Get suggestions
            suggestions = await self.search_service.get_suggestions_autocomplete(
                session=session,
                prefix=query,
                limit=5,
            )

        # Delete searching message
        await searching_msg.delete()

        # Display results
        if not results["results"]:
            await self._display_no_results(update, query, suggestions)
            return

        await self._display_search_results(
            update, results, query, 0
        )

    async def _display_search_results(
        self,
        update: Update,
        results: Dict,
        query: str,
        page: int = 0,
    ) -> None:
        """
        Display search results with pagination.

        Args:
            update: Telegram update
            results: Search results
            query: Search query
            page: Current page
        """
        items_per_page = 5
        total_pages = max(1, (results["total_count"] + items_per_page - 1) // items_per_page)
        
        start_idx = page * items_per_page
        end_idx = start_idx + items_per_page
        page_results = results["results"][start_idx:end_idx]

        if not page_results:
            await update.message.reply_text(
                "❌ لا توجد نتائج في هذه الصفحة."
            )
            return

        # Build results message
        message_text = f"🔍 *نتائج البحث عن:* `{escape_markdown(query)}`\n"
        message_text += f"📊 *عدد النتائج:* {results['total_count']}\n"
        message_text += f"📄 *صفحة:* {page + 1}/{total_pages}\n\n"

        keyboard = []
        for i, software in enumerate(page_results):
            # Truncate description
            desc = truncate_text(
                software.get("description", ""), 80
            )

            # Rating stars
            rating = software.get("rating", 0)
            stars = "⭐" * int(rating) + "☆" * (5 - int(rating))

            # Software info
            message_text += (
                f"*{start_idx + i + 1}\.* {escape_markdown(software['name'])}\n"
                f"📦 الإصدار: {escape_markdown(software.get('version', 'غير محدد'))}\n"
                f"💾 الحجم: {escape_markdown(format_file_size(software.get('file_size', 0)))}\n"
                f"📥 التحميلات: {software.get('download_count', 0)}\n"
                f"{stars}\n"
                f"_{escape_markdown(desc)}_\n\n"
            )

            # Add button for each result
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {software['name'][:30]}",
                    callback_data=f"download_{software['id']}"
                ),
                InlineKeyboardButton(
                    "📋 معلومات",
                    callback_data=f"info_{software['id']}"
                ),
            ])
            keyboard.append([
                InlineKeyboardButton(
                    "⭐", callback_data=f"rate_{software['id']}"
                ),
                InlineKeyboardButton(
                    "❤️", callback_data=f"fav_{software['id']}"
                ),
                InlineKeyboardButton(
                    "📤", callback_data=f"share_{software['id']}"
                ),
                InlineKeyboardButton(
                    "🔄 برامج مشابهة",
                    callback_data=f"similar_{software['id']}"
                ),
            ])

        # Pagination buttons
        nav_buttons = []
        if page > 0:
            nav_buttons.append(
                InlineKeyboardButton(
                    "⬅️ السابق",
                    callback_data=f"page_{query}_{page - 1}"
                )
            )
        if page < total_pages - 1:
            nav_buttons.append(
                InlineKeyboardButton(
                    "التالي ➡️",
                    callback_data=f"page_{query}_{page + 1}"
                )
            )
        if nav_buttons:
            keyboard.append(nav_buttons)

        # Add filter buttons
        keyboard.append([
            InlineKeyboardButton(
                "🔽 الأكثر تحميلاً",
                callback_data=f"sort_downloads_{query}"
            ),
            InlineKeyboardButton(
                "⭐ الأعلى تقييماً",
                callback_data=f"sort_rating_{query}"
            ),
        ])

        reply_markup = InlineKeyboardMarkup(keyboard)

        # Truncate message if too long
        if len(message_text) > 4000:
            message_text = message_text[:4000] + "\n\n... *والمزيد*"

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=reply_markup,
            disable_web_page_preview=True,
        )

    async def _display_no_results(
        self,
        update: Update,
        query: str,
        suggestions: List[str],
    ) -> None:
        """Display no results message with suggestions."""
        message_text = f"❌ *لا توجد نتائج لـ:* `{escape_markdown(query)}`\n\n"

        if suggestions:
            message_text += "💡 *اقتراحات:*\n"
            for sug in suggestions[:5]:
                if isinstance(sug, str):
                    message_text += f"• {escape_markdown(sug)}\n"

        message_text += "\n🔍 *جرب:*\n"
        message_text += "• استخدام كلمات أقل\n"
        message_text += "• التأكد من الإملاء\n"
        message_text += "• البحث باللغة الإنجليزية\n"
        message_text += "• تصفح /categories"

        keyboard = [[
            InlineKeyboardButton(
                "📂 تصفح الفئات",
                callback_data="categories"
            ),
            InlineKeyboardButton(
                "🔥 البرامج الشائعة",
                callback_data="popular"
            ),
        ]]

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def popular_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /popular command - show popular software."""
        async for session in db_manager.get_session():
            trending = await self.search_service.get_trending(session, limit=10)

        if not trending:
            await update.message.reply_text("❌ لا توجد بيانات متاحة حالياً.")
            return

        message_text = "🔥 *البرامج الشائعة*\n\n"
        keyboard = []

        for i, software in enumerate(trending, 1):
            message_text += (
                f"*{i}\.* {escape_markdown(software['name'])}\n"
                f"📥 {software['download_count']} تحميل\n\n"
            )
            keyboard.append([
                InlineKeyboardButton(
                    f"📥 {software['name'][:30]}",
                    callback_data=f"download_{software['id']}"
                ),
                InlineKeyboardButton(
                    "📋",
                    callback_data=f"info_{software['id']}"
                ),
            ])

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def trending_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /trending command."""
        await self.popular_command(update, context)

    async def categories_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /categories command."""
        async for session in db_manager.get_session():
            categories = await self.file_service.get_categories(session)

        if not categories:
            await update.message.reply_text("❌ لا توجد فئات متاحة.")
            return

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

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard_rows),
        )

    async def favorites_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /favorites command."""
        user_id = update.effective_user.id

        async for session in db_manager.get_session():
            favorites, total = await UserRepository.get_user_favorites(
                session, user_id, limit=20
            )

            if not favorites:
                await update.message.reply_text(
                    "⭐ *المفضلة فارغة*\n\n"
                    "أضف برامج إلى المفضلة بالضغط على ❤️",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            message_text = f"⭐ *المفضلة* ({total})\n\n"
            keyboard = []

            for fav in favorites:
                software = await SoftwareRepository.get_by_id(
                    session, fav["software_id"]
                )
                if software:
                    message_text += (
                        f"• {escape_markdown(software.name)}\n"
                        f"  📅 {get_relative_time(fav['added_at'])}\n\n"
                    )
                    keyboard.append([
                        InlineKeyboardButton(
                            f"📥 {software.name[:30]}",
                            callback_data=f"download_{software.id}"
                        ),
                        InlineKeyboardButton(
                            "❌ إزالة",
                            callback_data=f"unfav_{software.id}"
                        ),
                    ])

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
            disable_web_page_preview=True,
        )

    async def history_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /history command."""
        user_id = update.effective_user.id

        async for session in db_manager.get_session():
            history = await UserRepository.get_user_history(
                session, user_id, limit=10
            )

            if not history:
                await update.message.reply_text(
                    "📜 *سجل التحميلات فارغ*",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return

            message_text = "📜 *آخر التحميلات*\n\n"
            keyboard = []

            for item in history:
                software = await SoftwareRepository.get_by_id(
                    session, item["software_id"]
                )
                if software:
                    message_text += (
                        f"• {escape_markdown(software.name)}\n"
                        f"  📅 {get_relative_time(item['downloaded_at'])}\n\n"
                    )
                    keyboard.append([
                        InlineKeyboardButton(
                            f"📥 {software.name[:30]}",
                            callback_data=f"download_{software.id}"
                        ),
                    ])

        await update.message.reply_text(
            message_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard) if keyboard else None,
            disable_web_page_preview=True,
        )

    async def settings_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /settings command."""
        user = update.effective_user

        settings_text = (
            f"⚙️ *الإعدادات*\n\n"
            f"👤 *المستخدم:* {escape_markdown(user.first_name or '')}\n"
            f"🆔 *المعرف:* `{user.id}`\n"
            f"🌐 *اللغة:* العربية\n\n"
            f"*الإعدادات المتاحة:*\n"
        )

        keyboard = [
            [
                InlineKeyboardButton(
                    "🔔 الإشعارات",
                    callback_data="setting_notifications"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🌐 تغيير اللغة",
                    callback_data="setting_language"
                ),
            ],
            [
                InlineKeyboardButton(
                    "📊 إحصائياتي",
                    callback_data="setting_stats"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🗑️ مسح السجل",
                    callback_data="setting_clear_history"
                ),
            ],
        ]

        await update.message.reply_text(
            settings_text,
            parse_mode=ParseMode.MARKDOWN_V2,
            reply_markup=InlineKeyboardMarkup(keyboard),
        )

    async def contact_command(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle /contact command."""
        contact_text = (
            "📞 *للاتصال بالمشرف*\n\n"
            "إذا كان لديك استفسار أو مشكلة، يمكنك:\n"
            "• إرسال رسالة للمشرف\n"
            "• استخدام الأمر /report للإبلاغ عن مشكلة\n"
            "• التواصل عبر القناة الرسمية\n\n"
            "شكراً لاستخدامك البوت! 🙏"
        )

        await update.message.reply_text(
            contact_text,
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    def get_handlers(self) -> List:
        """Get all user handlers."""
        return [
            CommandHandler("start", self.start_command),
            CommandHandler("help", self.help_command),
            CommandHandler("search", self.search_command),
            CommandHandler("popular", self.popular_command),
            CommandHandler("trending", self.trending_command),
            CommandHandler("categories", self.categories_command),
            CommandHandler("favorites", self.favorites_command),
            CommandHandler("history", self.history_command),
            CommandHandler("settings", self.settings_command),
            CommandHandler("contact", self.contact_command),
            MessageHandler(
                filters.TEXT & ~filters.COMMAND,
                self.handle_message
            ),
        ]


# Global instance
user_handlers = UserHandlers()
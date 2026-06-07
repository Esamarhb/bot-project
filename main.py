#!/usr/bin/env python3
"""
Main entry point for the Telegram Bot application.
Initializes and runs the bot with all handlers.
"""

import asyncio
import signal
import sys
import logging
from datetime import datetime

from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    ContextTypes,
    Defaults,
)
from telegram.constants import ParseMode

from config import settings
from database import db_manager
from utils.logger import setup_logger
from utils.cache import cache_manager
from utils.security import security_manager
from services.notification_service import notification_service
from services.backup_service import backup_service
from handlers.user_handlers import user_handlers
from handlers.admin_handlers import admin_handlers
from handlers.callback_handlers import callback_handlers

# Setup logging
logger = setup_logger(
    name="bot",
    log_file=settings.log_file,
    level=settings.log_level,
    enable_json=False,
)


class TelegramBot:
    """Main bot application class."""

    def __init__(self):
        """Initialize bot application."""
        self.application: Application = None
        self._running = False

    async def initialize(self) -> None:
        """Initialize bot components."""
        logger.info("Initializing bot components...")

        try:
            # Initialize database
            await db_manager.initialize()
            logger.info("Database initialized")

            # Initialize cache
            if settings.use_redis:
                await cache_manager.initialize_redis()
            logger.info("Cache initialized")

            # Build application
            self.application = (
                ApplicationBuilder()
                .token(settings.bot_token)
                .defaults(Defaults(parse_mode=ParseMode.MARKDOWN_V2))
                .build()
            )

            # Set bot instance for notification service
            notification_service.set_bot(self.application.bot)

            # Register handlers
            self._register_handlers()

            # Register error handler
            self.application.add_error_handler(self._error_handler)

            logger.info("Bot initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}", exc_info=True)
            raise

    def _register_handlers(self) -> None:
        """Register all handlers."""
        # User handlers
        for handler in user_handlers.get_handlers():
            self.application.add_handler(handler)

        # Admin handlers
        for handler in admin_handlers.get_handlers():
            self.application.add_handler(handler)

        # Callback handlers (must be last for pattern matching)
        for handler in callback_handlers.get_handlers():
            self.application.add_handler(handler)

        logger.info("Handlers registered")

    async def _error_handler(
        self,
        update: object,
        context: ContextTypes.DEFAULT_TYPE
    ) -> None:
        """Handle errors."""
        logger.error(
            f"Update {update} caused error {context.error}",
            exc_info=context.error,
        )

        # Send error message to user if possible
        if isinstance(update, Update) and update.effective_message:
            try:
                await update.effective_message.reply_text(
                    "❌ *عذراً، حدث خطأ غير متوقع*\n\n"
                    "تم تسجيل الخطأ وسيتم معالجته قريباً.\n"
                    "يمكنك المحاولة مرة أخرى لاحقاً.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            except Exception:
                pass

    async def start(self) -> None:
        """Start the bot."""
        if self._running:
            logger.warning("Bot is already running")
            return

        try:
            await self.initialize()

            # Start the bot
            logger.info("Starting bot...")
            self._running = True

            # Start polling
            await self.application.initialize()
            await self.application.start()
            await self.application.updater.start_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
            )

            logger.info("Bot started successfully")
            logger.info(f"Bot username: @{(await self.application.bot.get_me()).username}")

            # Schedule backup task
            await self._schedule_backups()

            # Keep running
            while self._running:
                await asyncio.sleep(1)

        except Exception as e:
            logger.error(f"Failed to start bot: {e}", exc_info=True)
            raise

    async def stop(self) -> None:
        """Stop the bot gracefully."""
        if not self._running:
            return

        logger.info("Stopping bot...")
        self._running = False

        try:
            # Stop application
            if self.application:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()

            # Close database
            await db_manager.close()

            # Close cache
            await cache_manager.close()

            logger.info("Bot stopped successfully")

        except Exception as e:
            logger.error(f"Error stopping bot: {e}")

    async def _schedule_backups(self) -> None:
        """Schedule periodic backups."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler

        scheduler = AsyncIOScheduler()

        async def backup_task():
            logger.info("Running scheduled backup...")
            async for session in db_manager.get_session():
                result = await backup_service.create_backup(session)
                if result:
                    logger.info(f"Backup created: {result['name']}")
                else:
                    logger.error("Backup failed")

        scheduler.add_job(
            backup_task,
            'interval',
            hours=settings.backup_interval_hours,
            id='backup_job',
        )

        scheduler.start()
        logger.info(f"Backup scheduler started (every {settings.backup_interval_hours}h)")


async def main() -> None:
    """Main function to run the bot."""
    bot = TelegramBot()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(
            sig,
            lambda: asyncio.create_task(bot.stop())
        )

    try:
        await bot.start()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
    finally:
        await bot.stop()


if __name__ == "__main__":
    # Print banner
    print("""
╔══════════════════════════════════════════╗
║     Telegram Software Library Bot        ║
║          Starting Application...         ║
╚══════════════════════════════════════════╝
    """)

    # Run the bot
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nBot stopped by user")
    except Exception as e:
        print(f"\nFatal error: {e}")
        sys.exit(1)
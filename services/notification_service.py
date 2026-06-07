"""
Notification service module.
Handles user notifications and broadcast messages.
"""

from typing import List, Optional, Dict, Any
import logging
import asyncio
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from database import BroadcastMessage
from models.user import UserRepository
from utils.helpers import escape_markdown, chunk_list
from config import settings

logger = logging.getLogger(__name__)


class NotificationService:
    """Service for managing notifications and broadcasts."""

    def __init__(self, bot=None):
        """
        Initialize notification service.

        Args:
            bot: Telegram bot instance
        """
        self.bot = bot
        self.broadcast_chunk_size = 30  # Users per batch
        self.broadcast_delay = 0.05  # Delay between messages (seconds)

    def set_bot(self, bot) -> None:
        """Set bot instance."""
        self.bot = bot

    async def send_broadcast(
        self,
        session: AsyncSession,
        admin_id: int,
        message_text: str,
        target_users: Optional[List[int]] = None,
        parse_mode: str = "MarkdownV2",
    ) -> Dict[str, Any]:
        """
        Send broadcast message to users.

        Args:
            session: Database session
            admin_id: Admin user ID
            message_text: Message text to broadcast
            target_users: Specific user IDs (None for all users)
            parse_mode: Message parse mode

        Returns:
            Broadcast results
        """
        if not self.bot:
            raise ValueError("Bot instance not set")

        results = {
            "total_users": 0,
            "successful": 0,
            "failed": 0,
            "blocked": 0,
            "started_at": datetime.utcnow().isoformat(),
        }

        try:
            # Get users
            if target_users:
                users = target_users
            else:
                users_list, _ = await UserRepository.get_all_users(
                    session, limit=10000, only_active=True
                )
                users = [user.id for user in users_list]

            results["total_users"] = len(users)

            # Escape markdown if needed
            if parse_mode == "MarkdownV2":
                safe_message = message_text  # Already escaped by caller
            else:
                safe_message = message_text

            # Send in chunks
            user_chunks = chunk_list(users, self.broadcast_chunk_size)

            for chunk in user_chunks:
                tasks = []
                for user_id in chunk:
                    task = self._send_to_user(
                        user_id, safe_message, parse_mode
                    )
                    tasks.append(task)

                # Execute chunk concurrently
                chunk_results = await asyncio.gather(*tasks, return_exceptions=True)

                for result in chunk_results:
                    if isinstance(result, Exception):
                        results["failed"] += 1
                        logger.error(f"Broadcast error: {result}")
                    elif result == "blocked":
                        results["blocked"] += 1
                    elif result == "success":
                        results["successful"] += 1

                # Delay between chunks
                await asyncio.sleep(self.broadcast_delay)

            # Log broadcast
            broadcast = BroadcastMessage(
                admin_id=admin_id,
                message_text=message_text[:500],
                recipients_count=results["successful"],
            )
            session.add(broadcast)
            await session.flush()

            results["completed_at"] = datetime.utcnow().isoformat()
            logger.info(f"Broadcast complete: {results}")

        except Exception as e:
            logger.error(f"Broadcast failed: {e}", exc_info=True)
            results["error"] = str(e)

        return results

    async def _send_to_user(
        self,
        user_id: int,
        message: str,
        parse_mode: str = "MarkdownV2"
    ) -> str:
        """
        Send message to single user.

        Args:
            user_id: User ID
            message: Message text
            parse_mode: Parse mode

        Returns:
            Status string
        """
        try:
            await self.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode=parse_mode,
                disable_web_page_preview=True,
            )
            return "success"
        except Exception as e:
            error_msg = str(e).lower()
            if "blocked" in error_msg or "deactivated" in error_msg:
                return "blocked"
            elif "chat not found" in error_msg:
                return "not_found"
            else:
                logger.error(f"Failed to send to {user_id}: {e}")
                raise

    async def send_new_version_notification(
        self,
        session: AsyncSession,
        software_name: str,
        new_version: str,
        software_id: int,
    ) -> Dict[str, Any]:
        """
        Notify users about new version.

        Args:
            session: Database session
            software_name: Software name
            new_version: New version string
            software_id: Software ID

        Returns:
            Notification results
        """
        # Get users who downloaded this software
        from database import DownloadLog
        from sqlalchemy import select, distinct

        result = await session.execute(
            select(distinct(DownloadLog.user_id)).where(
                DownloadLog.software_id == software_id
            )
        )
        user_ids = result.scalars().all()

        if not user_ids:
            return {"notified": 0}

        # Create notification message
        message = (
            f"🆕 *تحديث جديد*\n\n"
            f"تم إضافة إصدار جديد من *{escape_markdown(software_name)}*\n"
            f"الإصدار: {escape_markdown(new_version)}\n\n"
            f"للتحميل، ابحث عن: `{escape_markdown(software_name)}`"
        )

        # Send notifications
        results = await self.send_broadcast(
            session=session,
            admin_id=0,  # System notification
            message_text=message,
            target_users=list(user_ids),
        )

        logger.info(
            f"Version notification sent for {software_name}: "
            f"{results['successful']} users notified"
        )

        return results

    async def send_maintenance_notification(
        self,
        session: AsyncSession,
        message: str,
    ) -> Dict[str, Any]:
        """Send maintenance notification to all users."""
        maintenance_message = (
            f"🔧 *إشعار صيانة*\n\n"
            f"{escape_markdown(message)}"
        )

        return await self.send_broadcast(
            session=session,
            admin_id=0,
            message_text=maintenance_message,
        )


# Global notification service
notification_service = NotificationService()
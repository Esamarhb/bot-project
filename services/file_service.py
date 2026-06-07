"""
File service module.
Handles file operations, indexing, and management.
"""

from typing import List, Dict, Optional, Any, BinaryIO
import logging
import json
from datetime import datetime
from pathlib import Path
import aiofiles
import os
from sqlalchemy.ext.asyncio import AsyncSession

from models.software import SoftwareRepository
from models.user import UserRepository
from utils.helpers import (
    format_file_size,
    generate_keywords,
    sanitize_input,
    clean_text,
)
from utils.cache import cache_manager
from config import settings

logger = logging.getLogger(__name__)


class FileService:
    """Service for managing software files and indexing."""

    ALLOWED_EXTENSIONS = {
        'apk', 'exe', 'msi', 'dmg', 'deb', 'rpm',
        'zip', 'rar', '7z', 'tar', 'gz', 'bz2',
        'pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx',
        'mp4', 'mkv', 'avi', 'mov', 'wmv',
        'mp3', 'wav', 'flac', 'aac', 'ogg',
        'jpg', 'jpeg', 'png', 'gif', 'bmp', 'svg',
        'iso', 'img', 'bin', 'cue',
        'txt', 'csv', 'json', 'xml', 'html',
    }

    MAX_FILE_SIZE_MB = 2000  # 2 GB max

    def __init__(self):
        """Initialize file service."""
        self.temp_dir = settings.base_dir / "temp"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    async def index_channel_message(
        self,
        session: AsyncSession,
        message_data: Dict[str, Any]
    ) -> Optional[Dict]:
        """
        Index a new file from channel message.

        Args:
            session: Database session
            message_data: Message data from Telegram

        Returns:
            Indexed software data or None
        """
        try:
            # Extract message data
            message_id = message_data.get("message_id")
            channel_id = message_data.get("channel_id", settings.channel_id)
            document = message_data.get("document")
            caption = message_data.get("caption", "")

            if not document:
                logger.warning("No document in message")
                return None

            # Extract file info
            file_name = document.get("file_name", "Unknown")
            file_size = document.get("file_size", 0) / (1024 * 1024)  # Convert to MB
            mime_type = document.get("mime_type", "")
            file_extension = Path(file_name).suffix.lower().lstrip(".")

            # Validate file
            if not self._validate_file(file_extension, file_size):
                logger.warning(f"File validation failed: {file_name}")
                return None

            # Parse caption for metadata
            metadata = self._parse_caption(caption)

            # Generate software info
            software_name = metadata.get("name", Path(file_name).stem)
            description = metadata.get("description", caption[:500] if caption else "")
            version = metadata.get("version", "1.0")
            category = metadata.get("category", self._detect_category(file_extension))

            # Check if already indexed
            existing = await SoftwareRepository.get_software_by_message_id(
                session, message_id, channel_id
            )

            if existing:
                logger.info(f"Software already indexed: {software_name}")
                return self._format_software_response(existing)

            # Add to database
            software = await SoftwareRepository.add_software(
                session=session,
                name=software_name,
                message_id=message_id,
                channel_id=channel_id,
                description=description,
                version=version,
                file_type=file_extension,
                file_size=file_size,
                category=category,
                metadata=metadata,
            )

            # Clear search cache
            await cache_manager.delete("search:*")

            logger.info(f"Indexed new software: {software_name} (ID: {software.id})")
            return self._format_software_response(software)

        except Exception as e:
            logger.error(f"Error indexing message: {e}", exc_info=True)
            return None

    async def bulk_index(
        self,
        session: AsyncSession,
        messages: List[Dict[str, Any]]
    ) -> Dict[str, int]:
        """
        Bulk index multiple messages.

        Args:
            session: Database session
            messages: List of message data

        Returns:
            Dictionary with indexing results
        """
        results = {
            "total": len(messages),
            "indexed": 0,
            "skipped": 0,
            "errors": 0,
        }

        for message in messages:
            try:
                result = await self.index_channel_message(session, message)
                if result:
                    results["indexed"] += 1
                else:
                    results["skipped"] += 1
            except Exception as e:
                logger.error(f"Bulk index error: {e}")
                results["errors"] += 1

        logger.info(f"Bulk indexing complete: {results}")
        return results

    async def reindex_all(self, session: AsyncSession) -> int:
        """
        Reindex all software entries.

        Args:
            session: Database session

        Returns:
            Number of reindexed items
        """
        count = await SoftwareRepository.reindex_all(session)

        # Clear all search cache
        await cache_manager.clear()

        logger.info(f"Reindexed {count} software entries")
        return count

    async def delete_software(
        self,
        session: AsyncSession,
        software_id: int,
        hard_delete: bool = False
    ) -> bool:
        """
        Delete software entry.

        Args:
            session: Database session
            software_id: Software ID
            hard_delete: If True, permanently delete

        Returns:
            True if deleted
        """
        success = await SoftwareRepository.delete_software(
            session, software_id, soft_delete=not hard_delete
        )

        if success:
            # Clear cache
            await cache_manager.delete(f"software:{software_id}")
            await cache_manager.delete("search:*")

        return success

    async def update_software(
        self,
        session: AsyncSession,
        software_id: int,
        **kwargs
    ) -> bool:
        """
        Update software metadata.

        Args:
            session: Database session
            software_id: Software ID
            **kwargs: Fields to update

        Returns:
            True if updated
        """
        success = await SoftwareRepository.update_software(
            session, software_id, **kwargs
        )

        if success:
            # Clear cache
            await cache_manager.delete(f"software:{software_id}")
            await cache_manager.delete("search:*")

        return success

    async def get_software_info(
        self,
        session: AsyncSession,
        software_id: int
    ) -> Optional[Dict]:
        """
        Get detailed software information.

        Args:
            session: Database session
            software_id: Software ID

        Returns:
            Software information dictionary
        """
        # Check cache
        cache_key = f"software:{software_id}"
        cached = await cache_manager.get(cache_key)
        if cached:
            return cached

        software = await SoftwareRepository.get_by_id(session, software_id)
        if not software:
            return None

        info = self._format_software_response(software)

        # Cache result
        await cache_manager.set(cache_key, info, 600)  # 10 minutes

        return info

    async def get_related_software(
        self,
        session: AsyncSession,
        software_id: int,
        limit: int = 5
    ) -> List[Dict]:
        """Get related software."""
        related = await SoftwareRepository.get_related_software(
            session, software_id, limit
        )

        return [
            self._format_software_response(sw)
            for sw in related
        ]

    async def get_categories(self, session: AsyncSession) -> List[str]:
        """Get all categories."""
        return await SoftwareRepository.get_categories(session)

    async def download_software(
        self,
        session: AsyncSession,
        software_id: int,
        user_id: int
    ) -> Optional[Dict]:
        """
        Process software download.

        Args:
            session: Database session
            software_id: Software ID
            user_id: User ID

        Returns:
            Download information
        """
        software = await SoftwareRepository.get_by_id(session, software_id)
        if not software:
            return None

        # Increment download count
        await SoftwareRepository.increment_download_count(session, software_id)

        # Log download
        await UserRepository.log_download(session, user_id, software_id)

        # Clear cache
        await cache_manager.delete(f"software:{software_id}")

        return {
            "software_id": software_id,
            "message_id": software.message_id,
            "channel_id": software.channel_id,
            "file_name": software.name,
            "file_type": software.file_type,
            "file_size": software.file_size,
        }

    def _validate_file(self, extension: str, size_mb: float) -> bool:
        """
        Validate file for indexing.

        Args:
            extension: File extension
            size_mb: File size in MB

        Returns:
            True if valid
        """
        if extension.lower() not in self.ALLOWED_EXTENSIONS:
            logger.warning(f"Extension not allowed: {extension}")
            return False

        if size_mb > self.MAX_FILE_SIZE_MB:
            logger.warning(f"File too large: {size_mb} MB")
            return False

        if size_mb <= 0:
            logger.warning("Invalid file size")
            return False

        return True

    def _parse_caption(self, caption: str) -> Dict[str, Any]:
        """
        Parse message caption for metadata.

        Args:
            caption: Message caption text

        Returns:
            Parsed metadata dictionary
        """
        metadata = {
            "name": None,
            "description": None,
            "version": None,
            "category": None,
            "tags": [],
        }

        if not caption:
            return metadata

        lines = caption.strip().split("\n")

        # First line is usually the name
        if lines:
            metadata["name"] = sanitize_input(lines[0], 200)

        # Look for metadata in lines
        for line in lines[1:]:
            line = line.strip()

            # Version
            if line.lower().startswith(("version:", "v:", "الإصدار:")):
                version = line.split(":", 1)[-1].strip()
                metadata["version"] = sanitize_input(version, 50)

            # Category
            elif line.lower().startswith(("category:", "type:", "الفئة:", "النوع:")):
                category = line.split(":", 1)[-1].strip()
                metadata["category"] = sanitize_input(category, 100)

            # Tags
            elif line.lower().startswith(("tags:", "keywords:", "وسوم:", "كلمات:")):
                tags_text = line.split(":", 1)[-1].strip()
                metadata["tags"] = [
                    tag.strip() for tag in tags_text.split(",")
                    if tag.strip()
                ]

            # Description (lines without prefix)
            elif not any(
                line.lower().startswith(prefix)
                for prefix in ["version:", "v:", "category:", "type:", "tags:", "keywords:"]
            ):
                if not metadata["description"]:
                    metadata["description"] = line
                else:
                    metadata["description"] += "\n" + line

        # Truncate description
        if metadata["description"]:
            metadata["description"] = sanitize_input(
                metadata["description"], 500
            )

        return metadata

    def _detect_category(self, extension: str) -> str:
        """
        Detect software category from file extension.

        Args:
            extension: File extension

        Returns:
            Category name
        """
        extension = extension.lower()

        # Mobile apps
        if extension == "apk":
            return "تطبيقات أندرويد"
        elif extension == "ipa":
            return "تطبيقات iOS"

        # Desktop apps
        elif extension in ("exe", "msi"):
            return "برامج ويندوز"
        elif extension == "dmg":
            return "برامج ماك"
        elif extension in ("deb", "rpm"):
            return "برامج لينكس"

        # Archives
        elif extension in ("zip", "rar", "7z", "tar", "gz", "bz2"):
            return "ملفات مضغوطة"

        # Documents
        elif extension in ("pdf", "doc", "docx"):
            return "مستندات"
        elif extension in ("xls", "xlsx"):
            return "جداول بيانات"
        elif extension in ("ppt", "pptx"):
            return "عروض تقديمية"

        # Media
        elif extension in ("mp4", "mkv", "avi", "mov", "wmv"):
            return "فيديو"
        elif extension in ("mp3", "wav", "flac", "aac", "ogg"):
            return "صوتيات"
        elif extension in ("jpg", "jpeg", "png", "gif", "bmp", "svg"):
            return "صور"

        # Other
        elif extension in ("iso", "img", "bin", "cue"):
            return "ملفات أقراص"
        elif extension in ("txt", "csv", "json", "xml", "html"):
            return "ملفات نصية"

        return "أخرى"

    def _format_software_response(self, software) -> Dict[str, Any]:
        """
        Format software object for response.

        Args:
            software: Software database object

        Returns:
            Formatted dictionary
        """
        avg_rating = 0
        if software.rating_count > 0:
            avg_rating = round(
                software.rating_sum / software.rating_count, 1
            )

        return {
            "id": software.id,
            "name": software.name,
            "description": software.description,
            "version": software.version,
            "file_type": software.file_type,
            "file_size": software.file_size,
            "file_size_formatted": format_file_size(software.file_size or 0),
            "category": software.category,
            "message_id": software.message_id,
            "channel_id": software.channel_id,
            "download_count": software.download_count,
            "search_count": software.search_count,
            "rating": avg_rating,
            "rating_count": software.rating_count,
            "keywords": json.loads(software.keywords) if software.keywords else [],
            "is_active": software.is_active,
            "added_date": software.added_date.isoformat() if software.added_date else None,
            "updated_date": software.updated_date.isoformat() if software.updated_date else None,
        }


# Global file service instance
file_service = FileService()
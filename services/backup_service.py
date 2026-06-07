"""
Backup service module.
Handles database backup, restore, and export operations.
"""

from typing import Dict, Any, Optional, List
import logging
import asyncio
import json
import shutil
from datetime import datetime, timedelta
from pathlib import Path
import aiofiles
import os
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from database import Base, Software, User
from utils.helpers import format_datetime
from config import settings

logger = logging.getLogger(__name__)


class BackupService:
    """Service for managing database backups."""

    def __init__(self):
        """Initialize backup service."""
        self.backup_dir = settings.backups_dir
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.max_backups = settings.backup_retention_days

    async def create_backup(
        self,
        session: AsyncSession,
        backup_type: str = "full"
    ) -> Optional[Dict[str, Any]]:
        """
        Create database backup.

        Args:
            session: Database session
            backup_type: Type of backup ('full', 'software', 'users')

        Returns:
            Backup information dictionary
        """
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_name = f"backup_{backup_type}_{timestamp}"
            backup_path = self.backup_dir / backup_name
            backup_path.mkdir(parents=True, exist_ok=True)

            backup_data = {
                "type": backup_type,
                "timestamp": timestamp,
                "created_at": datetime.utcnow().isoformat(),
            }

            if backup_type == "full":
                # Export all data
                await self._export_software(session, backup_path / "software.json")
                await self._export_users(session, backup_path / "users.json")
                backup_data["tables"] = ["software", "users"]

            elif backup_type == "software":
                await self._export_software(session, backup_path / "software.json")
                backup_data["tables"] = ["software"]

            elif backup_type == "users":
                await self._export_users(session, backup_path / "users.json")
                backup_data["tables"] = ["users"]

            # Save backup metadata
            async with aiofiles.open(
                backup_path / "metadata.json", "w", encoding="utf-8"
            ) as f:
                await f.write(json.dumps(backup_data, ensure_ascii=False, indent=2))

            # Create compressed archive
            archive_path = self.backup_dir / f"{backup_name}.zip"
            shutil.make_archive(
                str(self.backup_dir / backup_name),
                'zip',
                str(backup_path)
            )

            # Remove uncompressed directory
            shutil.rmtree(backup_path)

            # Clean old backups
            await self._cleanup_old_backups()

            logger.info(f"Backup created: {archive_path}")

            return {
                "name": backup_name,
                "path": str(archive_path),
                "size": os.path.getsize(archive_path),
                "timestamp": timestamp,
                "type": backup_type,
            }

        except Exception as e:
            logger.error(f"Backup creation failed: {e}", exc_info=True)
            return None

    async def restore_backup(
        self,
        session: AsyncSession,
        backup_name: str,
        restore_type: str = "full"
    ) -> bool:
        """
        Restore database from backup.

        Args:
            session: Database session
            backup_name: Backup archive name
            restore_type: What to restore ('full', 'software', 'users')

        Returns:
            True if restored successfully
        """
        try:
            # Find backup archive
            archive_path = self.backup_dir / f"{backup_name}.zip"
            if not archive_path.exists():
                logger.error(f"Backup not found: {backup_name}")
                return False

            # Extract archive
            extract_path = self.backup_dir / f"restore_{backup_name}"
            shutil.unpack_archive(str(archive_path), str(extract_path), 'zip')

            # Restore data
            if restore_type in ("full", "software"):
                software_file = extract_path / "software.json"
                if software_file.exists():
                    await self._import_software(session, software_file)

            if restore_type in ("full", "users"):
                users_file = extract_path / "users.json"
                if users_file.exists():
                    await self._import_users(session, users_file)

            # Clean up
            shutil.rmtree(extract_path)

            logger.info(f"Backup restored: {backup_name}")
            return True

        except Exception as e:
            logger.error(f"Backup restore failed: {e}", exc_info=True)
            return False

    async def export_data(
        self,
        session: AsyncSession,
        export_type: str = "software",
        format_type: str = "json"
    ) -> Optional[str]:
        """
        Export data in various formats.

        Args:
            session: Database session
            export_type: Type of data to export
            format_type: Export format ('json', 'csv')

        Returns:
            Path to exported file
        """
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            export_file = self.backup_dir / f"export_{export_type}_{timestamp}.{format_type}"

            if export_type == "software":
                data = await self._get_software_data(session)

                if format_type == "json":
                    async with aiofiles.open(export_file, "w", encoding="utf-8") as f:
                        await f.write(json.dumps(data, ensure_ascii=False, indent=2))

                elif format_type == "csv":
                    await self._export_to_csv(data, export_file)

            elif export_type == "users":
                data = await self._get_users_data(session)

                if format_type == "json":
                    async with aiofiles.open(export_file, "w", encoding="utf-8") as f:
                        await f.write(json.dumps(data, ensure_ascii=False, indent=2))

                elif format_type == "csv":
                    await self._export_to_csv(data, export_file)

            logger.info(f"Data exported: {export_file}")
            return str(export_file)

        except Exception as e:
            logger.error(f"Export failed: {e}", exc_info=True)
            return None

    async def _export_software(
        self,
        session: AsyncSession,
        file_path: Path
    ) -> None:
        """Export software data to JSON."""
        data = await self._get_software_data(session)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    async def _export_users(
        self,
        session: AsyncSession,
        file_path: Path
    ) -> None:
        """Export users data to JSON."""
        data = await self._get_users_data(session)

        async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(data, ensure_ascii=False, indent=2))

    async def _import_software(
        self,
        session: AsyncSession,
        file_path: Path
    ) -> None:
        """Import software data from JSON."""
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)

        for item in data:
            await session.execute(
                text("""
                    INSERT OR REPLACE INTO software 
                    (id, name, description, version, file_type, file_size, 
                     message_id, channel_id, keywords, added_date, is_active, 
                     download_count, search_count, category)
                    VALUES 
                    (:id, :name, :description, :version, :file_type, :file_size,
                     :message_id, :channel_id, :keywords, :added_date, :is_active,
                     :download_count, :search_count, :category)
                """),
                item
            )

        await session.commit()

    async def _import_users(
        self,
        session: AsyncSession,
        file_path: Path
    ) -> None:
        """Import users data from JSON."""
        async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
            content = await f.read()
            data = json.loads(content)

        for item in data:
            await session.execute(
                text("""
                    INSERT OR REPLACE INTO users 
                    (id, username, first_name, last_name, language_code, 
                     is_blocked, is_admin, created_at, last_activity)
                    VALUES 
                    (:id, :username, :first_name, :last_name, :language_code,
                     :is_blocked, :is_admin, :created_at, :last_activity)
                """),
                item
            )

        await session.commit()

    async def _get_software_data(
        self,
        session: AsyncSession
    ) -> List[Dict]:
        """Get all software data."""
        from sqlalchemy import select

        result = await session.execute(
            select(Software).where(Software.is_active == True)
        )
        software_list = result.scalars().all()

        return [
            {
                "id": sw.id,
                "name": sw.name,
                "description": sw.description,
                "version": sw.version,
                "file_type": sw.file_type,
                "file_size": sw.file_size,
                "message_id": sw.message_id,
                "channel_id": sw.channel_id,
                "keywords": sw.keywords,
                "added_date": sw.added_date.isoformat() if sw.added_date else None,
                "is_active": sw.is_active,
                "download_count": sw.download_count,
                "search_count": sw.search_count,
                "category": sw.category,
            }
            for sw in software_list
        ]

    async def _get_users_data(
        self,
        session: AsyncSession
    ) -> List[Dict]:
        """Get all users data."""
        from sqlalchemy import select

        result = await session.execute(select(User))
        users = result.scalars().all()

        return [
            {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "last_name": user.last_name,
                "language_code": user.language_code,
                "is_blocked": user.is_blocked,
                "is_admin": user.is_admin,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_activity": user.last_activity.isoformat() if user.last_activity else None,
            }
            for user in users
        ]

    async def _export_to_csv(
        self,
        data: List[Dict],
        file_path: Path
    ) -> None:
        """Export data to CSV format."""
        if not data:
            return

        import csv

        # Get headers from first item
        headers = list(data[0].keys())

        async with aiofiles.open(file_path, "w", encoding="utf-8", newline='') as f:
            # Write headers
            await f.write(','.join(headers) + '\n')

            # Write data
            for item in data:
                row = [str(item.get(h, "")) for h in headers]
                await f.write(','.join(row) + '\n')

    async def _cleanup_old_backups(self) -> None:
        """Remove old backup files."""
        try:
            cutoff_date = datetime.utcnow() - timedelta(days=self.max_backups)

            for backup_file in self.backup_dir.glob("backup_*.zip"):
                if backup_file.stat().st_mtime < cutoff_date.timestamp():
                    backup_file.unlink()
                    logger.info(f"Removed old backup: {backup_file}")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")

    async def list_backups(self) -> List[Dict]:
        """List all available backups."""
        backups = []

        for backup_file in sorted(
            self.backup_dir.glob("backup_*.zip"),
            key=lambda x: x.stat().st_mtime,
            reverse=True
        ):
            backups.append({
                "name": backup_file.stem,
                "size": backup_file.stat().st_size,
                "created_at": format_datetime(
                    datetime.fromtimestamp(backup_file.stat().st_mtime)
                ),
            })

        return backups

    async def delete_backup(self, backup_name: str) -> bool:
        """Delete a backup file."""
        try:
            backup_path = self.backup_dir / f"{backup_name}.zip"
            if backup_path.exists():
                backup_path.unlink()
                logger.info(f"Deleted backup: {backup_name}")
                return True
            return False
        except Exception as e:
            logger.error(f"Delete backup error: {e}")
            return False


# Global backup service instance
backup_service = BackupService()
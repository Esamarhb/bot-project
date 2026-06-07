"""
Software repository module.
Handles all software-related database operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import logging
from sqlalchemy import select, update, delete, func, or_, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import Software, UserFavorite, SoftwareRating, DownloadLog
from utils.helpers import clean_text, generate_keywords

logger = logging.getLogger(__name__)


class SoftwareRepository:
    """Repository for software database operations."""

    @staticmethod
    async def add_software(
        session: AsyncSession,
        name: str,
        message_id: int,
        channel_id: str,
        description: Optional[str] = None,
        version: Optional[str] = None,
        file_type: Optional[str] = None,
        file_size: Optional[float] = None,
        category: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> Software:
        """
        Add new software entry.

        Args:
            session: Database session
            name: Software name
            message_id: Telegram message ID
            channel_id: Channel ID/username
            description: Software description
            version: Software version
            file_type: File type
            file_size: File size in MB
            category: Software category
            metadata: Additional metadata

        Returns:
            Created Software object
        """
        # Generate keywords
        keywords = generate_keywords(name, description or "")

        software = Software(
            name=name,
            description=description,
            version=version,
            file_type=file_type,
            file_size=file_size,
            message_id=message_id,
            channel_id=channel_id,
            keywords=json.dumps(keywords, ensure_ascii=False),
            category=category,
            metadata=metadata,
        )

        session.add(software)
        await session.flush()
        await session.refresh(software)

        logger.info(f"Added software: {name} (ID: {software.id})")
        return software

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        software_id: int
    ) -> Optional[Software]:
        """
        Get software by ID.

        Args:
            session: Database session
            software_id: Software ID

        Returns:
            Software object or None
        """
        result = await session.execute(
            select(Software).where(
                Software.id == software_id,
                Software.is_active == True
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def search_software(
        session: AsyncSession,
        query: str,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        file_type: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> tuple[List[Software], int]:
        """
        Search software with various filters.

        Args:
            session: Database session
            query: Search query
            limit: Results limit
            offset: Results offset
            category: Filter by category
            file_type: Filter by file type
            sort_by: Sort method (relevance, downloads, rating, date)

        Returns:
            Tuple of (software list, total count)
        """
        clean_query = clean_text(query)

        # Build search conditions
        conditions = [Software.is_active == True]

        if clean_query:
            search_condition = or_(
                Software.name.ilike(f"%{clean_query}%"),
                Software.description.ilike(f"%{clean_query}%"),
                Software.keywords.ilike(f"%{clean_query}%"),
                Software.category.ilike(f"%{clean_query}%"),
            )
            conditions.append(search_condition)

        if category:
            conditions.append(Software.category == category)

        if file_type:
            conditions.append(Software.file_type == file_type)

        # Build query
        base_query = select(Software).where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        total_result = await session.execute(count_query)
        total_count = total_result.scalar()

        # Apply sorting
        if sort_by == "downloads":
            base_query = base_query.order_by(desc(Software.download_count))
        elif sort_by == "rating":
            base_query = base_query.order_by(desc(Software.rating_sum / func.nullif(Software.rating_count, 0)))
        elif sort_by == "date":
            base_query = base_query.order_by(desc(Software.added_date))
        else:  # relevance
            base_query = base_query.order_by(desc(Software.search_count))

        # Apply pagination
        base_query = base_query.limit(limit).offset(offset)

        # Execute query
        result = await session.execute(base_query)
        software_list = result.scalars().all()

        return list(software_list), total_count

    @staticmethod
    async def update_software(
        session: AsyncSession,
        software_id: int,
        **kwargs
    ) -> bool:
        """
        Update software information.

        Args:
            session: Database session
            software_id: Software ID
            **kwargs: Fields to update

        Returns:
            True if updated successfully
        """
        valid_fields = {
            'name', 'description', 'version', 'file_type',
            'file_size', 'category', 'is_active', 'metadata'
        }

        update_data = {
            k: v for k, v in kwargs.items()
            if k in valid_fields and v is not None
        }

        if not update_data:
            return False

        # Update keywords if name or description changed
        if 'name' in update_data or 'description' in update_data:
            software = await SoftwareRepository.get_by_id(session, software_id)
            if software:
                name = update_data.get('name', software.name)
                description = update_data.get('description', software.description)
                keywords = generate_keywords(name, description or "")
                update_data['keywords'] = json.dumps(keywords, ensure_ascii=False)

        await session.execute(
            update(Software)
            .where(Software.id == software_id)
            .values(**update_data)
        )

        logger.info(f"Updated software ID {software_id}: {update_data}")
        return True

    @staticmethod
    async def delete_software(
        session: AsyncSession,
        software_id: int,
        soft_delete: bool = True
    ) -> bool:
        """
        Delete or deactivate software.

        Args:
            session: Database session
            software_id: Software ID
            soft_delete: If True, just deactivate; if False, hard delete

        Returns:
            True if deleted successfully
        """
        if soft_delete:
            await session.execute(
                update(Software)
                .where(Software.id == software_id)
                .values(is_active=False)
            )
            logger.info(f"Soft deleted software ID {software_id}")
        else:
            await session.execute(
                delete(Software).where(Software.id == software_id)
            )
            logger.info(f"Hard deleted software ID {software_id}")

        return True

    @staticmethod
    async def increment_search_count(
        session: AsyncSession,
        software_id: int
    ) -> None:
        """Increment search count for software."""
        await session.execute(
            update(Software)
            .where(Software.id == software_id)
            .values(search_count=Software.search_count + 1)
        )

    @staticmethod
    async def increment_download_count(
        session: AsyncSession,
        software_id: int
    ) -> None:
        """Increment download count for software."""
        await session.execute(
            update(Software)
            .where(Software.id == software_id)
            .values(download_count=Software.download_count + 1)
        )

    @staticmethod
    async def get_related_software(
        session: AsyncSession,
        software_id: int,
        limit: int = 5
    ) -> List[Software]:
        """
        Get related software based on category and keywords.

        Args:
            session: Database session
            software_id: Source software ID
            limit: Number of related items

        Returns:
            List of related Software objects
        """
        software = await SoftwareRepository.get_by_id(session, software_id)
        if not software:
            return []

        conditions = [
            Software.id != software_id,
            Software.is_active == True,
        ]

        # Same category
        if software.category:
            conditions.append(Software.category == software.category)

        # Get results
        query = (
            select(Software)
            .where(and_(*conditions))
            .order_by(desc(Software.download_count))
            .limit(limit)
        )

        result = await session.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def get_software_by_message_id(
        session: AsyncSession,
        message_id: int,
        channel_id: str
    ) -> Optional[Software]:
        """Get software by message ID."""
        result = await session.execute(
            select(Software).where(
                Software.message_id == message_id,
                Software.channel_id == channel_id
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_categories(session: AsyncSession) -> List[str]:
        """Get all unique categories."""
        result = await session.execute(
            select(Software.category)
            .where(Software.is_active == True)
            .distinct()
            .order_by(Software.category)
        )
        return [row[0] for row in result if row[0]]

    @staticmethod
    async def reindex_all(session: AsyncSession) -> int:
        """
        Reindex all software entries (regenerate keywords).

        Args:
            session: Database session

        Returns:
            Number of reindexed items
        """
        result = await session.execute(
            select(Software).where(Software.is_active == True)
        )
        software_list = result.scalars().all()

        count = 0
        for software in software_list:
            keywords = generate_keywords(software.name, software.description or "")
            software.keywords = json.dumps(keywords, ensure_ascii=False)
            count += 1

        await session.flush()
        logger.info(f"Reindexed {count} software entries")
        return count
"""
User repository module.
Handles all user-related database operations.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging
from sqlalchemy import select, update, delete, func, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database import User, UserFavorite, SoftwareRating, SearchLog, DownloadLog

logger = logging.getLogger(__name__)


class UserRepository:
    """Repository for user database operations."""

    @staticmethod
    async def get_or_create_user(
        session: AsyncSession,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        language_code: str = "ar"
    ) -> User:
        """
        Get existing user or create new one.

        Args:
            session: Database session
            user_id: Telegram user ID
            username: Telegram username
            first_name: User's first name
            last_name: User's last name
            language_code: User's language code

        Returns:
            User object
        """
        # Try to get existing user
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        user = result.scalar_one_or_none()

        if user:
            # Update user info if changed
            if username and username != user.username:
                user.username = username
            if first_name and first_name != user.first_name:
                user.first_name = first_name
            if last_name and last_name != user.last_name:
                user.last_name = last_name
            if language_code and language_code != user.language_code:
                user.language_code = language_code

            # Update last activity
            user.last_activity = datetime.utcnow()
            await session.flush()
            return user

        # Create new user
        user = User(
            id=user_id,
            username=username,
            first_name=first_name,
            last_name=last_name,
            language_code=language_code,
            preferences={},
        )
        session.add(user)
        await session.flush()
        await session.refresh(user)

        logger.info(f"Created new user: {user_id} (@{username})")
        return user

    @staticmethod
    async def get_user_by_id(
        session: AsyncSession,
        user_id: int
    ) -> Optional[User]:
        """Get user by ID."""
        result = await session.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def block_user(session: AsyncSession, user_id: int) -> bool:
        """Block a user."""
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_blocked=True)
        )
        logger.info(f"Blocked user: {user_id}")
        return True

    @staticmethod
    async def unblock_user(session: AsyncSession, user_id: int) -> bool:
        """Unblock a user."""
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(is_blocked=False)
        )
        logger.info(f"Unblocked user: {user_id}")
        return True

    @staticmethod
    async def get_all_users(
        session: AsyncSession,
        limit: int = 100,
        offset: int = 0,
        only_active: bool = True
    ) -> tuple[List[User], int]:
        """
        Get all users with pagination.

        Args:
            session: Database session
            limit: Results limit
            offset: Results offset
            only_active: Only return non-blocked users

        Returns:
            Tuple of (users list, total count)
        """
        conditions = []
        if only_active:
            conditions.append(User.is_blocked == False)

        # Get total count
        count_query = select(func.count()).select_from(User)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        total_result = await session.execute(count_query)
        total_count = total_result.scalar()

        # Get users
        query = select(User)
        if conditions:
            query = query.where(and_(*conditions))
        query = query.order_by(desc(User.last_activity)).limit(limit).offset(offset)

        result = await session.execute(query)
        users = result.scalars().all()

        return list(users), total_count

    @staticmethod
    async def get_total_users(session: AsyncSession) -> int:
        """Get total number of users."""
        result = await session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar()

    @staticmethod
    async def get_active_users_count(
        session: AsyncSession,
        days: int = 1
    ) -> int:
        """Get count of active users in last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        result = await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity >= cutoff_date
            )
        )
        return result.scalar()

    @staticmethod
    async def add_favorite(
        session: AsyncSession,
        user_id: int,
        software_id: int
    ) -> bool:
        """Add software to user favorites."""
        # Check if already favorited
        existing = await session.execute(
            select(UserFavorite).where(
                UserFavorite.user_id == user_id,
                UserFavorite.software_id == software_id
            )
        )
        if existing.scalar_one_or_none():
            return False

        favorite = UserFavorite(
            user_id=user_id,
            software_id=software_id
        )
        session.add(favorite)
        await session.flush()

        logger.info(f"User {user_id} favorited software {software_id}")
        return True

    @staticmethod
    async def remove_favorite(
        session: AsyncSession,
        user_id: int,
        software_id: int
    ) -> bool:
        """Remove software from user favorites."""
        await session.execute(
            delete(UserFavorite).where(
                UserFavorite.user_id == user_id,
                UserFavorite.software_id == software_id
            )
        )
        return True

    @staticmethod
    async def get_user_favorites(
        session: AsyncSession,
        user_id: int,
        limit: int = 20,
        offset: int = 0
    ) -> tuple[List[Dict], int]:
        """Get user's favorite software."""
        # Get total count
        count_result = await session.execute(
            select(func.count())
            .select_from(UserFavorite)
            .where(UserFavorite.user_id == user_id)
        )
        total_count = count_result.scalar()

        # Get favorites
        result = await session.execute(
            select(UserFavorite)
            .where(UserFavorite.user_id == user_id)
            .order_by(desc(UserFavorite.added_at))
            .limit(limit)
            .offset(offset)
        )
        favorites = result.scalars().all()

        return [
            {
                "id": fav.id,
                "software_id": fav.software_id,
                "added_at": fav.added_at,
            }
            for fav in favorites
        ], total_count

    @staticmethod
    async def rate_software(
        session: AsyncSession,
        user_id: int,
        software_id: int,
        rating: int,
        review: Optional[str] = None
    ) -> bool:
        """
        Rate software (1-5 stars).

        Args:
            session: Database session
            user_id: User ID
            software_id: Software ID
            rating: Rating (1-5)
            review: Optional review text

        Returns:
            True if rated successfully
        """
        if not 1 <= rating <= 5:
            return False

        # Check existing rating
        existing = await session.execute(
            select(SoftwareRating).where(
                SoftwareRating.user_id == user_id,
                SoftwareRating.software_id == software_id
            )
        )
        existing_rating = existing.scalar_one_or_none()

        if existing_rating:
            # Update existing rating
            existing_rating.rating = rating
            if review:
                existing_rating.review = review
        else:
            # Create new rating
            new_rating = SoftwareRating(
                user_id=user_id,
                software_id=software_id,
                rating=rating,
                review=review,
            )
            session.add(new_rating)

        # Update software rating stats
        from database import Software
        ratings_result = await session.execute(
            select(SoftwareRating.rating).where(
                SoftwareRating.software_id == software_id
            )
        )
        all_ratings = ratings_result.scalars().all()

        await session.execute(
            update(Software)
            .where(Software.id == software_id)
            .values(
                rating_sum=sum(all_ratings),
                rating_count=len(all_ratings)
            )
        )

        await session.flush()
        logger.info(f"User {user_id} rated software {software_id}: {rating}★")
        return True

    @staticmethod
    async def get_user_rating(
        session: AsyncSession,
        user_id: int,
        software_id: int
    ) -> Optional[Dict]:
        """Get user's rating for specific software."""
        result = await session.execute(
            select(SoftwareRating).where(
                SoftwareRating.user_id == user_id,
                SoftwareRating.software_id == software_id
            )
        )
        rating = result.scalar_one_or_none()

        if not rating:
            return None

        return {
            "rating": rating.rating,
            "review": rating.review,
            "created_at": rating.created_at,
        }

    @staticmethod
    async def log_search(
        session: AsyncSession,
        user_id: int,
        query: str,
        results_count: int
    ) -> None:
        """Log search query."""
        search_log = SearchLog(
            user_id=user_id,
            query=query,
            results_count=results_count,
        )
        session.add(search_log)
        await session.flush()

    @staticmethod
    async def log_download(
        session: AsyncSession,
        user_id: int,
        software_id: int
    ) -> None:
        """Log software download."""
        download_log = DownloadLog(
            user_id=user_id,
            software_id=software_id,
        )
        session.add(download_log)
        await session.flush()

    @staticmethod
    async def get_user_history(
        session: AsyncSession,
        user_id: int,
        limit: int = 10
    ) -> List[Dict]:
        """Get user's download history."""
        result = await session.execute(
            select(DownloadLog)
            .where(DownloadLog.user_id == user_id)
            .order_by(desc(DownloadLog.downloaded_at))
            .limit(limit)
        )
        logs = result.scalars().all()

        return [
            {
                "software_id": log.software_id,
                "downloaded_at": log.downloaded_at,
            }
            for log in logs
        ]

    @staticmethod
    async def update_preferences(
        session: AsyncSession,
        user_id: int,
        preferences: Dict
    ) -> bool:
        """Update user preferences."""
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(preferences=preferences)
        )
        return True

    @staticmethod
    async def get_user_stats(
        session: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """Get user statistics."""
        # Get download count
        download_result = await session.execute(
            select(func.count())
            .select_from(DownloadLog)
            .where(DownloadLog.user_id == user_id)
        )
        downloads = download_result.scalar()

        # Get search count
        search_result = await session.execute(
            select(func.count())
            .select_from(SearchLog)
            .where(SearchLog.user_id == user_id)
        )
        searches = search_result.scalar()

        # Get favorites count
        favorites_result = await session.execute(
            select(func.count())
            .select_from(UserFavorite)
            .where(UserFavorite.user_id == user_id)
        )
        favorites = favorites_result.scalar()

        return {
            "downloads": downloads,
            "searches": searches,
            "favorites": favorites,
        }
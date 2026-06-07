"""
Analytics repository module.
Handles statistics and analytics operations.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
from sqlalchemy import select, func, and_, desc, extract
from sqlalchemy.ext.asyncio import AsyncSession

from database import (
    Software, User, SearchLog, DownloadLog,
    SoftwareRating, UserFavorite
)

logger = logging.getLogger(__name__)


class AnalyticsRepository:
    """Repository for analytics and statistics."""

    @staticmethod
    async def get_dashboard_stats(session: AsyncSession) -> Dict[str, Any]:
        """
        Get dashboard statistics.

        Returns:
            Dictionary with various statistics
        """
        # Total users
        total_users_result = await session.execute(
            select(func.count()).select_from(User)
        )
        total_users = total_users_result.scalar()

        # Active users today
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        active_today_result = await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity >= today
            )
        )
        active_today = active_today_result.scalar()

        # Active users this month
        month_start = today.replace(day=1)
        active_month_result = await session.execute(
            select(func.count()).select_from(User).where(
                User.last_activity >= month_start
            )
        )
        active_month = active_month_result.scalar()

        # Total software
        total_software_result = await session.execute(
            select(func.count()).select_from(Software).where(
                Software.is_active == True
            )
        )
        total_software = total_software_result.scalar()

        # Total searches
        total_searches_result = await session.execute(
            select(func.count()).select_from(SearchLog)
        )
        total_searches = total_searches_result.scalar()

        # Total downloads
        total_downloads_result = await session.execute(
            select(func.count()).select_from(DownloadLog)
        )
        total_downloads = total_downloads_result.scalar()

        # Searches today
        searches_today_result = await session.execute(
            select(func.count()).select_from(SearchLog).where(
                SearchLog.searched_at >= today
            )
        )
        searches_today = searches_today_result.scalar()

        # Downloads today
        downloads_today_result = await session.execute(
            select(func.count()).select_from(DownloadLog).where(
                DownloadLog.downloaded_at >= today
            )
        )
        downloads_today = downloads_today_result.scalar()

        return {
            "users": {
                "total": total_users,
                "active_today": active_today,
                "active_month": active_month,
            },
            "software": {
                "total": total_software,
            },
            "activity": {
                "total_searches": total_searches,
                "total_downloads": total_downloads,
                "searches_today": searches_today,
                "downloads_today": downloads_today,
            }
        }

    @staticmethod
    async def get_most_searched(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get most searched software."""
        result = await session.execute(
            select(
                Software.name,
                Software.search_count,
                Software.download_count,
                Software.id
            )
            .where(Software.is_active == True)
            .order_by(desc(Software.search_count))
            .limit(limit)
        )
        items = result.all()

        return [
            {
                "id": item[3],
                "name": item[0],
                "search_count": item[1],
                "download_count": item[2],
            }
            for item in items
        ]

    @staticmethod
    async def get_most_downloaded(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get most downloaded software."""
        result = await session.execute(
            select(
                Software.name,
                Software.download_count,
                Software.search_count,
                Software.id,
                Software.rating_sum,
                Software.rating_count,
            )
            .where(Software.is_active == True)
            .order_by(desc(Software.download_count))
            .limit(limit)
        )
        items = result.all()

        return [
            {
                "id": item[3],
                "name": item[0],
                "download_count": item[1],
                "search_count": item[2],
                "avg_rating": round(item[4] / item[5], 1) if item[5] > 0 else 0,
            }
            for item in items
        ]

    @staticmethod
    async def get_top_rated(
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get top rated software."""
        result = await session.execute(
            select(
                Software.name,
                Software.rating_sum,
                Software.rating_count,
                Software.id,
                Software.download_count,
            )
            .where(
                Software.is_active == True,
                Software.rating_count > 0
            )
            .order_by(
                desc(Software.rating_sum / Software.rating_count)
            )
            .limit(limit)
        )
        items = result.all()

        return [
            {
                "id": item[3],
                "name": item[0],
                "avg_rating": round(item[1] / item[2], 1) if item[2] > 0 else 0,
                "rating_count": item[2],
                "download_count": item[4],
            }
            for item in items
        ]

    @staticmethod
    async def get_search_trends(
        session: AsyncSession,
        days: int = 7
    ) -> List[Dict]:
        """Get search trends for last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await session.execute(
            select(
                func.date(SearchLog.searched_at).label('date'),
                func.count().label('count')
            )
            .where(SearchLog.searched_at >= cutoff_date)
            .group_by(func.date(SearchLog.searched_at))
            .order_by('date')
        )
        trends = result.all()

        return [
            {"date": str(trend[0]), "count": trend[1]}
            for trend in trends
        ]

    @staticmethod
    async def get_download_trends(
        session: AsyncSession,
        days: int = 7
    ) -> List[Dict]:
        """Get download trends for last N days."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await session.execute(
            select(
                func.date(DownloadLog.downloaded_at).label('date'),
                func.count().label('count')
            )
            .where(DownloadLog.downloaded_at >= cutoff_date)
            .group_by(func.date(DownloadLog.downloaded_at))
            .order_by('date')
        )
        trends = result.all()

        return [
            {"date": str(trend[0]), "count": trend[1]}
            for trend in trends
        ]

    @staticmethod
    async def get_category_stats(
        session: AsyncSession
    ) -> List[Dict]:
        """Get statistics by category."""
        result = await session.execute(
            select(
                Software.category,
                func.count(Software.id),
                func.sum(Software.download_count),
                func.avg(
                    Software.rating_sum / func.nullif(Software.rating_count, 0)
                )
            )
            .where(
                Software.is_active == True,
                Software.category.isnot(None)
            )
            .group_by(Software.category)
            .order_by(desc(func.count(Software.id)))
        )
        stats = result.all()

        return [
            {
                "category": stat[0],
                "count": stat[1],
                "total_downloads": stat[2] or 0,
                "avg_rating": round(stat[3] or 0, 1),
            }
            for stat in stats
        ]

    @staticmethod
    async def get_user_growth(
        session: AsyncSession,
        days: int = 30
    ) -> List[Dict]:
        """Get user growth statistics."""
        cutoff_date = datetime.utcnow() - timedelta(days=days)

        result = await session.execute(
            select(
                func.date(User.created_at).label('date'),
                func.count().label('count')
            )
            .where(User.created_at >= cutoff_date)
            .group_by(func.date(User.created_at))
            .order_by('date')
        )
        growth = result.all()

        return [
            {"date": str(item[0]), "new_users": item[1]}
            for item in growth
        ]

    @staticmethod
    async def get_hourly_activity(
        session: AsyncSession
    ) -> Dict[int, int]:
        """Get hourly activity distribution."""
        # Get download activity by hour
        result = await session.execute(
            select(
                extract('hour', DownloadLog.downloaded_at).label('hour'),
                func.count().label('count')
            )
            .group_by('hour')
            .order_by('hour')
        )
        hourly_data = result.all()

        activity = {hour: 0 for hour in range(24)}
        for hour, count in hourly_data:
            activity[int(hour)] = count

        return activity

    @staticmethod
    async def get_user_engagement(
        session: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """Get engagement stats for specific user."""
        # Total searches
        searches_result = await session.execute(
            select(func.count()).select_from(SearchLog).where(
                SearchLog.user_id == user_id
            )
        )
        total_searches = searches_result.scalar()

        # Total downloads
        downloads_result = await session.execute(
            select(func.count()).select_from(DownloadLog).where(
                DownloadLog.user_id == user_id
            )
        )
        total_downloads = downloads_result.scalar()

        # Favorite categories
        from database import Software
        fav_categories_result = await session.execute(
            select(Software.category, func.count(Software.id))
            .join(DownloadLog, DownloadLog.software_id == Software.id)
            .where(DownloadLog.user_id == user_id)
            .group_by(Software.category)
            .order_by(desc(func.count(Software.id)))
            .limit(5)
        )
        favorite_categories = [
            {"category": row[0], "count": row[1]}
            for row in fav_categories_result.all()
        ]

        # Average rating given
        ratings_result = await session.execute(
            select(func.avg(SoftwareRating.rating))
            .where(SoftwareRating.user_id == user_id)
        )
        avg_rating = ratings_result.scalar() or 0

        return {
            "total_searches": total_searches,
            "total_downloads": total_downloads,
            "favorite_categories": favorite_categories,
            "average_rating_given": round(avg_rating, 1),
        }
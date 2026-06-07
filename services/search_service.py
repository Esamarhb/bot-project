"""
Search service module.
Provides intelligent search with fuzzy matching and suggestions.
"""

from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime
from fuzzywuzzy import fuzz, process
from sqlalchemy.ext.asyncio import AsyncSession

from models.software import SoftwareRepository
from models.analytics import AnalyticsRepository
from utils.helpers import clean_text, generate_cache_key
from utils.cache import cache_manager

logger = logging.getLogger(__name__)


class SearchService:
    """Intelligent search service with caching and suggestions."""

    def __init__(self):
        """Initialize search service."""
        self.cache_ttl = 300  # 5 minutes cache
        self.min_query_length = 2
        self.max_results = 50
        self.similarity_threshold = 60  # Minimum similarity score

    async def search(
        self,
        session: AsyncSession,
        query: str,
        user_id: int,
        limit: int = 10,
        offset: int = 0,
        category: Optional[str] = None,
        file_type: Optional[str] = None,
        sort_by: str = "relevance",
    ) -> Dict:
        """
        Perform intelligent search.

        Args:
            session: Database session
            query: Search query
            user_id: User ID for logging
            limit: Results limit
            offset: Results offset
            category: Category filter
            file_type: File type filter
            sort_by: Sort method

        Returns:
            Dictionary with search results and metadata
        """
        clean_query = clean_text(query)

        # Check cache first
        cache_key = generate_cache_key(
            "search", clean_query, limit, offset,
            category or "all", file_type or "all", sort_by
        )

        cached_result = await cache_manager.get(cache_key)
        if cached_result:
            logger.debug(f"Cache hit for search: {clean_query}")
            return cached_result

        # Perform search
        if len(clean_query) >= self.min_query_length:
            results, total_count = await SoftwareRepository.search_software(
                session=session,
                query=clean_query,
                limit=limit,
                offset=offset,
                category=category,
                file_type=file_type,
                sort_by=sort_by,
            )

            # Apply fuzzy matching for better results
            if results:
                results = self._apply_fuzzy_ranking(results, clean_query)

            # Get suggestions if few results
            suggestions = []
            if total_count < 5 and len(clean_query) > 2:
                suggestions = await self._get_suggestions(
                    session, clean_query
                )
        else:
            # Query too short, return popular items
            results = []
            total_count = 0
            suggestions = ["يرجى إدخال كلمة بحث أطول (حرفين على الأقل)"]

            # Get popular software
            popular = await AnalyticsRepository.get_most_downloaded(
                session, limit=limit
            )
            if popular:
                # Convert to software objects
                software_ids = [item["id"] for item in popular]
                software_list = []
                for sid in software_ids:
                    sw = await SoftwareRepository.get_by_id(session, sid)
                    if sw:
                        software_list.append(sw)
                results = software_list
                total_count = len(results)

        # Format results
        formatted_results = [
            self._format_software_result(sw) for sw in results
        ]

        response = {
            "results": formatted_results,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "query": clean_query,
            "suggestions": suggestions[:5] if suggestions else [],
        }

        # Cache results
        await cache_manager.set(cache_key, response, self.cache_ttl)

        # Log search
        await SoftwareRepository.log_search(
            session=session,
            user_id=user_id,
            query=clean_query,
            results_count=total_count,
        )

        return response

    def _apply_fuzzy_ranking(
        self,
        results: List,
        query: str
    ) -> List:
        """
        Apply fuzzy matching to re-rank results.

        Args:
            results: List of Software objects
            query: Search query

        Returns:
            Re-ranked results
        """
        scored_results = []
        for software in results:
            # Calculate similarity scores
            name_score = fuzz.partial_ratio(
                query.lower(),
                software.name.lower()
            )
            desc_score = fuzz.partial_ratio(
                query.lower(),
                (software.description or "").lower()
            )

            # Weighted score (name is more important)
            final_score = (name_score * 0.7) + (desc_score * 0.3)

            # Boost by popularity
            popularity_boost = min(software.download_count / 1000, 10)
            final_score += popularity_boost

            scored_results.append((software, final_score))

        # Sort by score
        scored_results.sort(key=lambda x: x[1], reverse=True)

        return [item[0] for item in scored_results]

    async def _get_suggestions(
        self,
        session: AsyncSession,
        query: str
    ) -> List[str]:
        """
        Get search suggestions based on similar queries.

        Args:
            session: Database session
            query: Search query

        Returns:
            List of suggested queries
        """
        suggestions = set()

        # Get all software names
        from database import Software
        from sqlalchemy import select

        result = await session.execute(
            select(Software.name).where(Software.is_active == True)
        )
        all_names = result.scalars().all()

        # Find similar names
        for name in all_names:
            similarity = fuzz.partial_ratio(query.lower(), name.lower())
            if similarity > self.similarity_threshold:
                suggestions.add(name)

            if len(suggestions) >= 5:
                break

        return list(suggestions)[:5]

    def _format_software_result(self, software) -> Dict:
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
            "category": software.category,
            "message_id": software.message_id,
            "channel_id": software.channel_id,
            "download_count": software.download_count,
            "rating": avg_rating,
            "rating_count": software.rating_count,
            "added_date": software.added_date.isoformat() if software.added_date else None,
        }

    async def get_suggestions_autocomplete(
        self,
        session: AsyncSession,
        prefix: str,
        limit: int = 5
    ) -> List[str]:
        """
        Get autocomplete suggestions.

        Args:
            session: Database session
            prefix: Input prefix
            limit: Max suggestions

        Returns:
            List of suggestions
        """
        clean_prefix = clean_text(prefix)

        if len(clean_prefix) < 2:
            return []

        # Check cache
        cache_key = generate_cache_key("autocomplete", clean_prefix, limit)
        cached = await cache_manager.get(cache_key)
        if cached:
            return cached

        # Search for matching names
        from database import Software
        from sqlalchemy import select

        result = await session.execute(
            select(Software.name)
            .where(
                Software.is_active == True,
                Software.name.ilike(f"{clean_prefix}%")
            )
            .order_by(Software.search_count.desc())
            .limit(limit)
        )

        suggestions = list(result.scalars().all())

        # Cache results
        await cache_manager.set(cache_key, suggestions, self.cache_ttl)

        return suggestions

    async def get_trending(
        self,
        session: AsyncSession,
        limit: int = 10
    ) -> List[Dict]:
        """Get trending software."""
        trending = await AnalyticsRepository.get_most_downloaded(
            session, limit=limit
        )

        return [
            {
                "id": item["id"],
                "name": item["name"],
                "download_count": item["download_count"],
                "avg_rating": item.get("avg_rating", 0),
            }
            for item in trending
        ]

    async def get_recommendations(
        self,
        session: AsyncSession,
        user_id: int,
        limit: int = 5
    ) -> List[Dict]:
        """
        Get personalized recommendations for user.

        Args:
            session: Database session
            user_id: User ID
            limit: Max recommendations

        Returns:
            List of recommended software
        """
        # Get user's favorite categories
        from database import DownloadLog, Software
        from sqlalchemy import select, func, and_, desc

        # Get user's most downloaded categories
        result = await session.execute(
            select(
                Software.category,
                func.count(DownloadLog.id).label('count')
            )
            .join(DownloadLog, DownloadLog.software_id == Software.id)
            .where(
                DownloadLog.user_id == user_id,
                Software.category.isnot(None)
            )
            .group_by(Software.category)
            .order_by(desc('count'))
            .limit(3)
        )
        favorite_categories = [row[0] for row in result.all()]

        if not favorite_categories:
            # No history, return trending
            return await self.get_trending(session, limit)

        # Get recommended software from favorite categories
        # Excluding already downloaded ones
        downloaded_result = await session.execute(
            select(DownloadLog.software_id).where(
                DownloadLog.user_id == user_id
            )
        )
        downloaded_ids = set(downloaded_result.scalars().all())

        conditions = [
            Software.is_active == True,
            Software.category.in_(favorite_categories),
        ]

        if downloaded_ids:
            conditions.append(Software.id.notin_(downloaded_ids))

        result = await session.execute(
            select(Software)
            .where(and_(*conditions))
            .order_by(desc(Software.download_count))
            .limit(limit)
        )
        recommendations = result.scalars().all()

        return [
            self._format_software_result(sw)
            for sw in recommendations
        ]


# Global search service instance
search_service = SearchService()
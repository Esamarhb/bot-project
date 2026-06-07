"""
Database management module using SQLAlchemy with async support.
Provides database connection, session management, and model definitions.
"""

from typing import AsyncGenerator, Optional, Any
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
    AsyncEngine
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    Text, ForeignKey, Index, JSON, BigInteger
)
from sqlalchemy.sql import func
from datetime import datetime
import logging

from config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base model class for all database models."""
    pass


class DatabaseManager:
    """Manages database connections and sessions."""

    def __init__(self, database_url: str):
        """
        Initialize database manager.

        Args:
            database_url: Database connection URL
        """
        self.database_url = database_url
        self.engine: Optional[AsyncEngine] = None
        self.session_factory: Optional[async_sessionmaker] = None

    async def initialize(self) -> None:
        """Initialize database engine and create tables."""
        try:
            self.engine = create_async_engine(
                self.database_url,
                echo=False,
                pool_size=20,
                max_overflow=10,
                pool_pre_ping=True,
            )

            self.session_factory = async_sessionmaker(
                self.engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            # Create all tables
            async with self.engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            logger.info("Database initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def get_session(self) -> AsyncGenerator[AsyncSession, None]:
        """
        Get database session.

        Yields:
            AsyncSession: Database session
        """
        if not self.session_factory:
            raise RuntimeError("Database not initialized")

        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def close(self) -> None:
        """Close database connections."""
        if self.engine:
            await self.engine.dispose()
            logger.info("Database connections closed")


# Database Models
class Software(Base):
    """Software/file model for the digital library."""

    __tablename__ = "software"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=True)
    version: Mapped[str] = mapped_column(String(50), nullable=True)
    file_type: Mapped[str] = mapped_column(String(50), nullable=True)
    file_size: Mapped[float] = mapped_column(Float, nullable=True)  # Size in MB
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    keywords: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array of keywords
    added_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    updated_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    search_count: Mapped[int] = mapped_column(Integer, default=0)
    rating_sum: Mapped[int] = mapped_column(Integer, default=0)
    rating_count: Mapped[int] = mapped_column(Integer, default=0)
    category: Mapped[str] = mapped_column(String(100), nullable=True)
    metadata: Mapped[dict] = mapped_column(JSON, nullable=True)

    __table_args__ = (
        Index("idx_software_name", "name"),
        Index("idx_software_keywords", "keywords"),
        Index("idx_software_category", "category"),
        Index("idx_software_active", "is_active"),
    )


class User(Base):
    """Telegram user model."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str] = mapped_column(String(255), nullable=True)
    language_code: Mapped[str] = mapped_column(String(10), default="ar")
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )
    last_activity: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now()
    )
    search_count: Mapped[int] = mapped_column(Integer, default=0)
    download_count: Mapped[int] = mapped_column(Integer, default=0)
    preferences: Mapped[dict] = mapped_column(JSON, nullable=True)


class SearchLog(Base):
    """Search history log."""

    __tablename__ = "search_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    results_count: Mapped[int] = mapped_column(Integer, default=0)
    searched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_search_logs_user_id", "user_id"),
        Index("idx_search_logs_searched_at", "searched_at"),
    )


class DownloadLog(Base):
    """Download history log."""

    __tablename__ = "download_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    software_id: Mapped[int] = mapped_column(Integer, ForeignKey("software.id"))
    downloaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_download_logs_user_id", "user_id"),
        Index("idx_download_logs_software_id", "software_id"),
    )


class UserFavorite(Base):
    """User favorites model."""

    __tablename__ = "user_favorites"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    software_id: Mapped[int] = mapped_column(Integer, ForeignKey("software.id"))
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_user_favorites_user_id", "user_id"),
        Index("idx_user_favorites_software_id", "software_id"),
    )


class SoftwareRating(Base):
    """Software ratings by users."""

    __tablename__ = "software_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    software_id: Mapped[int] = mapped_column(Integer, ForeignKey("software.id"))
    rating: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5 stars
    review: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )

    __table_args__ = (
        Index("idx_software_ratings_software_id", "software_id"),
        Index("idx_software_ratings_user_id", "user_id"),
    )


class BroadcastMessage(Base):
    """Broadcast message history."""

    __tablename__ = "broadcast_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    message_text: Mapped[str] = mapped_column(Text, nullable=False)
    recipients_count: Mapped[int] = mapped_column(Integer, default=0)
    sent_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now()
    )


# Global database manager instance
db_manager = DatabaseManager(settings.database_url)
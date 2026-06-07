"""
Configuration module for the Telegram Bot application.
Handles all environment variables and application settings.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from pathlib import Path
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Bot Configuration
    bot_token: str = Field(..., env="BOT_TOKEN")
    channel_id: str = Field(..., env="CHANNEL_ID")
    admin_ids: List[int] = Field(default_factory=list, env="ADMIN_IDS")

    @validator("admin_ids", pre=True)
    def parse_admin_ids(cls, value) -> List[int]:
        """Parse admin IDs from comma-separated string."""
        if isinstance(value, str):
            return [int(id_.strip()) for id_ in value.split(",") if id_.strip()]
        return value

    # Database Configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///database/bot.db",
        env="DATABASE_URL"
    )

    # Redis Configuration
    redis_url: Optional[str] = Field(default=None, env="REDIS_URL")
    use_redis: bool = Field(default=False, env="USE_REDIS")

    # Backup Configuration
    backup_interval_hours: int = Field(default=24, env="BACKUP_INTERVAL_HOURS")
    backup_retention_days: int = Field(default=7, env="BACKUP_RETENTION_DAYS")

    # Rate Limiting
    rate_limit_requests: int = Field(default=30, env="RATE_LIMIT_REQUESTS")
    rate_limit_period_seconds: int = Field(default=60, env="RATE_LIMIT_PERIOD_SECONDS")

    # Logging
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    log_file: str = Field(default="logs/bot.log", env="LOG_FILE")

    # Maintenance Mode
    maintenance_mode: bool = Field(default=False, env="MAINTENANCE_MODE")

    # Application Paths
    base_dir: Path = Path(__file__).parent
    database_dir: Path = base_dir / "database"
    logs_dir: Path = base_dir / "logs"
    backups_dir: Path = base_dir / "backups"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False
    }

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._create_directories()

    def _create_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for directory in [self.database_dir, self.logs_dir, self.backups_dir]:
            directory.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
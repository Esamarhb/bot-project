"""
Utility modules for the Telegram bot.
Provides logging, caching, security, and helper functions.
"""

from .logger import setup_logger, CustomFormatter, JSONFormatter
from .cache import CacheManager, cache_manager
from .security import (
    SecurityManager,
    RateLimiter,
    InputValidator,
    FloodProtection,
    security_manager,
)
from .helpers import (
    format_file_size,
    clean_text,
    generate_keywords,
    sanitize_input,
    truncate_text,
    format_datetime,
    get_relative_time,
    escape_markdown,
    parse_json_field,
    generate_cache_key,
    chunk_list,
    calculate_rating_stats,
)

__all__ = [
    # Logger
    "setup_logger",
    "CustomFormatter",
    "JSONFormatter",
    # Cache
    "CacheManager",
    "cache_manager",
    # Security
    "SecurityManager",
    "RateLimiter",
    "InputValidator",
    "FloodProtection",
    "security_manager",
    # Helpers
    "format_file_size",
    "clean_text",
    "generate_keywords",
    "sanitize_input",
    "truncate_text",
    "format_datetime",
    "get_relative_time",
    "escape_markdown",
    "parse_json_field",
    "generate_cache_key",
    "chunk_list",
    "calculate_rating_stats",
]
"""
Helper functions for the Telegram bot.
Utility functions for formatting, text processing, and more.
"""

from typing import List, Optional, Dict, Any
import re
import unicodedata
from datetime import datetime, timedelta
import json


def format_file_size(size_mb: float) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_mb: Size in megabytes

    Returns:
        Formatted size string
    """
    if size_mb >= 1024:
        return f"{size_mb / 1024:.2f} GB"
    elif size_mb >= 1:
        return f"{size_mb:.2f} MB"
    elif size_mb >= 0.001:
        return f"{size_mb * 1024:.2f} KB"
    else:
        return f"{size_mb * 1024 * 1024:.0f} bytes"


def clean_text(text: str) -> str:
    """
    Clean and normalize text for search.

    Args:
        text: Input text

    Returns:
        Cleaned text
    """
    if not text:
        return ""

    # Convert to lowercase
    text = text.lower()

    # Remove accents and diacritics
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if not unicodedata.combining(c))

    # Remove special characters but keep alphanumeric and spaces
    text = re.sub(r'[^\w\s\-.]', '', text)

    # Remove extra whitespace
    text = ' '.join(text.split())

    return text.strip()


def generate_keywords(name: str, description: str = "") -> List[str]:
    """
    Generate keywords from software name and description.

    Args:
        name: Software name
        description: Software description

    Returns:
        List of keywords
    """
    keywords = set()

    # Add name variations
    clean_name = clean_text(name)
    keywords.add(clean_name)

    # Split into words
    words = clean_name.split()
    keywords.update(words)

    # Add description words
    if description:
        clean_desc = clean_text(description)
        desc_words = clean_desc.split()
        # Add longer words (>3 chars) from description
        keywords.update([w for w in desc_words if len(w) > 3])

    # Remove common words
    stop_words = {
        'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at',
        'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are',
        'was', 'were', 'be', 'been', 'being', 'have', 'has',
        'had', 'do', 'does', 'did', 'will', 'would', 'could',
        'should', 'may', 'might', 'can', 'shall', 'you', 'your',
        'we', 'they', 'them', 'this', 'that', 'these', 'those',
        'it', 'its', 'ال', 'في', 'من', 'على', 'مع', 'هو', 'هي',
    }
    keywords = keywords - stop_words

    return list(keywords)[:20]  # Limit to top 20 keywords


def sanitize_input(text: str, max_length: int = 500) -> str:
    """
    Sanitize user input.

    Args:
        text: Input text
        max_length: Maximum length

    Returns:
        Sanitized text
    """
    if not text:
        return ""

    # Truncate
    text = text[:max_length]

    # Remove HTML/XML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Remove control characters
    text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')

    return text.strip()


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    Truncate text to specified length.

    Args:
        text: Input text
        max_length: Maximum length
        suffix: Suffix to add when truncated

    Returns:
        Truncated text
    """
    if not text or len(text) <= max_length:
        return text or ""

    return text[:max_length - len(suffix)] + suffix


def format_datetime(dt: datetime, format_type: str = "full") -> str:
    """
    Format datetime for display.

    Args:
        dt: Datetime object
        format_type: Format type ('full', 'date', 'time', 'relative')

    Returns:
        Formatted datetime string
    """
    if not dt:
        return "N/A"

    if format_type == "date":
        return dt.strftime("%Y-%m-%d")
    elif format_type == "time":
        return dt.strftime("%H:%M:%S")
    elif format_type == "relative":
        return get_relative_time(dt)
    else:  # full
        return dt.strftime("%Y-%m-%d %H:%M:%S")


def get_relative_time(dt: datetime) -> str:
    """
    Get relative time string.

    Args:
        dt: Datetime object

    Returns:
        Relative time string
    """
    now = datetime.utcnow()
    diff = now - dt

    if diff < timedelta(minutes=1):
        return "الآن"
    elif diff < timedelta(hours=1):
        minutes = int(diff.total_seconds() / 60)
        return f"منذ {minutes} دقيقة"
    elif diff < timedelta(days=1):
        hours = int(diff.total_seconds() / 3600)
        return f"منذ {hours} ساعة"
    elif diff < timedelta(days=30):
        days = diff.days
        return f"منذ {days} يوم"
    elif diff < timedelta(days=365):
        months = int(diff.days / 30)
        return f"منذ {months} شهر"
    else:
        years = int(diff.days / 365)
        return f"منذ {years} سنة"


def escape_markdown(text: str) -> str:
    """
    Escape special characters for MarkdownV2.

    Args:
        text: Input text

    Returns:
        Escaped text
    """
    if not text:
        return ""

    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)


def parse_json_field(value: Optional[str]) -> Any:
    """
    Parse JSON field from database.

    Args:
        value: JSON string or None

    Returns:
        Parsed value
    """
    if not value:
        return None

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def generate_cache_key(prefix: str, *args) -> str:
    """
    Generate cache key from prefix and arguments.

    Args:
        prefix: Cache key prefix
        *args: Additional key parts

    Returns:
        Cache key string
    """
    key_parts = [prefix]
    key_parts.extend(str(arg) for arg in args)
    return ":".join(key_parts)


def chunk_list(lst: List, chunk_size: int) -> List[List]:
    """
    Split list into chunks.

    Args:
        lst: Input list
        chunk_size: Size of each chunk

    Returns:
        List of chunks
    """
    return [lst[i:i + chunk_size] for i in range(0, len(lst), chunk_size)]


def calculate_rating_stats(ratings: List[int]) -> Dict[str, Any]:
    """
    Calculate rating statistics.

    Args:
        ratings: List of rating values (1-5)

    Returns:
        Dictionary with rating stats
    """
    if not ratings:
        return {
            "average": 0,
            "count": 0,
            "distribution": {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
        }

    distribution = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    for rating in ratings:
        if 1 <= rating <= 5:
            distribution[rating] += 1

    average = sum(ratings) / len(ratings)

    return {
        "average": round(average, 1),
        "count": len(ratings),
        "distribution": distribution
    }
"""
Test helper functions.
"""

import pytest
from datetime import datetime, timedelta

from utils.helpers import (
    format_file_size,
    clean_text,
    generate_keywords,
    sanitize_input,
    truncate_text,
    escape_markdown,
    generate_cache_key,
    chunk_list,
    calculate_rating_stats,
)


class TestFormatFileSize:
    """Test file size formatting."""

    def test_bytes(self):
        assert format_file_size(0.0005) == "512 bytes"

    def test_kilobytes(self):
        assert format_file_size(0.5) == "512.00 KB"

    def test_megabytes(self):
        assert format_file_size(50) == "50.00 MB"
        assert format_file_size(500.75) == "500.75 MB"

    def test_gigabytes(self):
        assert format_file_size(1500) == "1.46 GB"
        assert format_file_size(2048) == "2.00 GB"


class TestCleanText:
    """Test text cleaning."""

    def test_lowercase_conversion(self):
        assert clean_text("HELLO") == "hello"

    def test_special_characters(self):
        assert clean_text("Hello, World! @#$") == "hello world"

    def test_arabic_text(self):
        assert clean_text("مرحبا بالعالم") == "مرحبا بالعالم"

    def test_empty_text(self):
        assert clean_text("") == ""
        assert clean_text(None) == ""


class TestGenerateKeywords:
    """Test keyword generation."""

    def test_basic_keywords(self):
        keywords = generate_keywords("Google Chrome Browser")
        assert "google" in keywords
        assert "chrome" in keywords
        assert "browser" in keywords

    def test_with_description(self):
        keywords = generate_keywords(
            "Photoshop",
            "Professional image editing software"
        )
        assert "photoshop" in keywords
        assert "professional" in keywords
        assert "editing" in keywords

    def test_stop_words_removed(self):
        keywords = generate_keywords(
            "The Best Software in the World"
        )
        assert "the" not in keywords
        assert "in" not in keywords
        assert "best" in keywords
        assert "software" in keywords


class TestSanitizeInput:
    """Test input sanitization."""

    def test_html_removal(self):
        assert sanitize_input("<script>alert('xss')</script>") == "alert('xss')"

    def test_control_characters(self):
        assert sanitize_input("Hello\x00\x01World") == "HelloWorld"

    def test_truncation(self):
        result = sanitize_input("A" * 1000, max_length=10)
        assert len(result) == 10

    def test_empty_input(self):
        assert sanitize_input("") == ""
        assert sanitize_input(None) == ""


class TestTruncateText:
    """Test text truncation."""

    def test_short_text(self):
        assert truncate_text("Hello", 10) == "Hello"

    def test_long_text(self):
        result = truncate_text("Hello World, this is a long text", 15)
        assert result == "Hello World,..."
        assert len(result) <= 15

    def test_custom_suffix(self):
        result = truncate_text("Hello World", 8, "...more")
        assert result == "H...more"


class TestEscapeMarkdown:
    """Test markdown escaping."""

    def test_special_characters(self):
        assert escape_markdown("Hello *World*") == "Hello \\*World\\*"
        assert escape_markdown("Test _underscore_") == "Test \\_underscore\\_"
        assert escape_markdown("[link]") == "\\[link\\]"

    def test_normal_text(self):
        assert escape_markdown("Hello World") == "Hello World"

    def test_empty_text(self):
        assert escape_markdown("") == ""
        assert escape_markdown(None) == ""


class TestCacheKey:
    """Test cache key generation."""

    def test_basic_key(self):
        key = generate_cache_key("search", "chrome", "10")
        assert key == "search:chrome:10"

    def test_multiple_args(self):
        key = generate_cache_key("user", 123, "favorites", 1)
        assert key == "user:123:favorites:1"

    def test_single_prefix(self):
        key = generate_cache_key("stats")
        assert key == "stats"


class TestChunkList:
    """Test list chunking."""

    def test_basic_chunking(self):
        result = chunk_list([1, 2, 3, 4, 5], 2)
        assert result == [[1, 2], [3, 4], [5]]

    def test_exact_division(self):
        result = chunk_list([1, 2, 3, 4], 2)
        assert result == [[1, 2], [3, 4]]

    def test_empty_list(self):
        result = chunk_list([], 3)
        assert result == []

    def test_chunk_size_larger_than_list(self):
        result = chunk_list([1, 2, 3], 10)
        assert result == [[1, 2, 3]]


class TestCalculateRatingStats:
    """Test rating statistics calculation."""

    def test_basic_stats(self):
        stats = calculate_rating_stats([4, 5, 3, 4, 5])
        assert stats["count"] == 5
        assert stats["average"] == 4.2
        assert stats["distribution"] == {1: 0, 2: 0, 3: 1, 4: 2, 5: 2}

    def test_empty_ratings(self):
        stats = calculate_rating_stats([])
        assert stats["count"] == 0
        assert stats["average"] == 0

    def test_single_rating(self):
        stats = calculate_rating_stats([5])
        assert stats["count"] == 1
        assert stats["average"] == 5.0

    def test_invalid_ratings_ignored(self):
        stats = calculate_rating_stats([1, 2, 6, 0, 3])  # 6 and 0 are invalid
        assert stats["count"] == 5  # Total count includes all
        assert stats["distribution"][3] == 1  # Valid ratings counted
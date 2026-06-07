"""
Security module for the Telegram bot.
Handles rate limiting, input validation, and flood protection.
"""

from typing import Dict, Optional, Tuple
from datetime import datetime, timedelta
import re
import hashlib
import logging
from collections import defaultdict
from cachetools import TTLCache

from config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using sliding window algorithm."""

    def __init__(self, max_requests: int = 30, period_seconds: int = 60):
        """
        Initialize rate limiter.

        Args:
            max_requests: Maximum requests allowed in the period
            period_seconds: Time period in seconds
        """
        self.max_requests = max_requests
        self.period_seconds = period_seconds
        self._requests: Dict[int, list] = defaultdict(list)

    def is_allowed(self, user_id: int) -> Tuple[bool, int]:
        """
        Check if user is allowed to make a request.

        Args:
            user_id: Telegram user ID

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.period_seconds)

        # Clean old requests
        self._requests[user_id] = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]

        # Check if limit exceeded
        if len(self._requests[user_id]) >= self.max_requests:
            remaining = 0
            return False, remaining

        # Add new request
        self._requests[user_id].append(now)
        remaining = self.max_requests - len(self._requests[user_id])

        return True, remaining

    def get_remaining(self, user_id: int) -> int:
        """Get remaining requests for user."""
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.period_seconds)

        self._requests[user_id] = [
            req_time for req_time in self._requests[user_id]
            if req_time > window_start
        ]

        return max(0, self.max_requests - len(self._requests[user_id]))


class InputValidator:
    """Input validation and sanitization."""

    # Patterns for validation
    USERNAME_PATTERN = re.compile(r'^[a-zA-Z0-9_]{3,32}$')
    SOFTWARE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9\s\-_.()\[\]{}]{1,200}$')
    SAFE_TEXT_PATTERN = re.compile(r'^[\w\s\-_.()\[\]{}@#&+\-,;:!?%$*=<>/\'"]+$')
    SQL_INJECTION_PATTERNS = [
        re.compile(r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER)\b)", re.IGNORECASE),
        re.compile(r"(--|;|/\*|\*/|@@|@)"),
        re.compile(r"('(''|[^'])*')"),
    ]

    @staticmethod
    def sanitize_text(text: str, max_length: int = 500) -> str:
        """
        Sanitize text input.

        Args:
            text: Input text
            max_length: Maximum allowed length

        Returns:
            Sanitized text
        """
        if not text:
            return ""

        # Truncate
        text = text[:max_length]

        # Remove control characters
        text = ''.join(char for char in text if ord(char) >= 32 or char == '\n')

        # Strip whitespace
        text = text.strip()

        return text

    @staticmethod
    def validate_software_name(name: str) -> bool:
        """
        Validate software name.

        Args:
            name: Software name

        Returns:
            True if valid
        """
        if not name or len(name) > 200:
            return False
        return bool(InputValidator.SOFTWARE_NAME_PATTERN.match(name))

    @staticmethod
    def detect_sql_injection(text: str) -> bool:
        """
        Detect potential SQL injection attempts.

        Args:
            text: Input text to check

        Returns:
            True if SQL injection detected
        """
        if not text:
            return False

        for pattern in InputValidator.SQL_INJECTION_PATTERNS:
            if pattern.search(text):
                logger.warning(f"SQL injection pattern detected: {pattern.pattern}")
                return True

        return False

    @staticmethod
    def validate_file_type(file_type: str) -> bool:
        """Validate file type."""
        allowed_types = {
            'apk', 'exe', 'msi', 'dmg', 'deb', 'rpm',
            'zip', 'rar', '7z', 'tar', 'gz',
            'pdf', 'doc', 'docx', 'xls', 'xlsx',
            'mp4', 'mkv', 'avi', 'mp3', 'wav',
        }
        return file_type.lower() in allowed_types


class FloodProtection:
    """Flood protection for messages."""

    def __init__(self, max_messages: int = 5, window_seconds: int = 10):
        """
        Initialize flood protection.

        Args:
            max_messages: Maximum messages in window
            window_seconds: Time window in seconds
        """
        self.max_messages = max_messages
        self.window_seconds = window_seconds
        self._message_times: Dict[int, list] = defaultdict(list)
        self._warnings: Dict[int, int] = defaultdict(int)
        self._blocked: TTLCache = TTLCache(maxsize=1000, ttl=3600)

    def is_flooding(self, user_id: int) -> bool:
        """
        Check if user is flooding.

        Args:
            user_id: User ID

        Returns:
            True if flooding detected
        """
        # Check if blocked
        if user_id in self._blocked:
            return True

        now = datetime.utcnow()
        window_start = now - timedelta(seconds=self.window_seconds)

        # Clean old messages
        self._message_times[user_id] = [
            msg_time for msg_time in self._message_times[user_id]
            if msg_time > window_start
        ]

        # Add new message
        self._message_times[user_id].append(now)

        # Check for flood
        if len(self._message_times[user_id]) > self.max_messages:
            self._warnings[user_id] += 1

            if self._warnings[user_id] >= 3:
                # Block user for 1 hour
                self._blocked[user_id] = True
                logger.warning(f"User {user_id} blocked for flooding")
                return True

            logger.warning(f"Flood detected from user {user_id}")
            return True

        return False

    def reset_warnings(self, user_id: int) -> None:
        """Reset flood warnings for user."""
        self._warnings[user_id] = 0
        self._message_times[user_id].clear()


class SecurityManager:
    """Main security manager combining all security features."""

    def __init__(self):
        """Initialize security manager."""
        self.rate_limiter = RateLimiter(
            max_requests=settings.rate_limit_requests,
            period_seconds=settings.rate_limit_period_seconds
        )
        self.input_validator = InputValidator()
        self.flood_protection = FloodProtection()
        logger.info("Security manager initialized")

    async def check_request(self, user_id: int) -> Tuple[bool, str]:
        """
        Comprehensive security check for requests.

        Args:
            user_id: User ID

        Returns:
            Tuple of (is_allowed, reason)
        """
        # Check flood protection
        if self.flood_protection.is_flooding(user_id):
            return False, "flood_detected"

        # Check rate limit
        is_allowed, remaining = self.rate_limiter.is_allowed(user_id)
        if not is_allowed:
            return False, "rate_limit_exceeded"

        return True, "ok"

    def sanitize_input(self, text: str, max_length: int = 500) -> str:
        """
        Sanitize user input.

        Args:
            text: Input text
            max_length: Maximum length

        Returns:
            Sanitized text
        """
        # Sanitize
        text = self.input_validator.sanitize_text(text, max_length)

        # Check for SQL injection
        if self.input_validator.detect_sql_injection(text):
            logger.warning(f"SQL injection attempt blocked")
            return ""

        return text


# Global security manager
security_manager = SecurityManager()
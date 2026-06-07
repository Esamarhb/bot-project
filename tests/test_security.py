"""
Test security features.
"""

import pytest
from datetime import datetime, timedelta

from utils.security import (
    RateLimiter,
    InputValidator,
    FloodProtection,
    SecurityManager,
)


class TestRateLimiter:
    """Test rate limiter."""

    def test_allows_requests_within_limit(self):
        """Test that requests within limit are allowed."""
        limiter = RateLimiter(max_requests=5, period_seconds=60)
        
        for _ in range(5):
            allowed, remaining = limiter.is_allowed(12345)
            assert allowed == True
        
        assert remaining == 0

    def test_blocks_requests_over_limit(self):
        """Test that requests over limit are blocked."""
        limiter = RateLimiter(max_requests=3, period_seconds=60)
        
        for _ in range(3):
            limiter.is_allowed(12345)
        
        # 4th request should be blocked
        allowed, remaining = limiter.is_allowed(12345)
        assert allowed == False
        assert remaining == 0

    def test_different_users_independent(self):
        """Test that rate limits are per-user."""
        limiter = RateLimiter(max_requests=2, period_seconds=60)
        
        # User 1 uses all requests
        limiter.is_allowed(111)
        limiter.is_allowed(111)
        
        # User 1 should be blocked
        allowed, _ = limiter.is_allowed(111)
        assert allowed == False
        
        # User 2 should still be allowed
        allowed, _ = limiter.is_allowed(222)
        assert allowed == True


class TestInputValidator:
    """Test input validation."""

    def test_sanitize_text(self):
        """Test text sanitization."""
        validator = InputValidator()
        
        # Normal text
        result = validator.sanitize_text("Hello World")
        assert result == "Hello World"
        
        # Text with control characters
        result = validator.sanitize_text("Hello\x00World")
        assert result == "HelloWorld"
        
        # Text too long
        long_text = "A" * 1000
        result = validator.sanitize_text(long_text, max_length=100)
        assert len(result) == 100

    def test_sql_injection_detection(self):
        """Test SQL injection detection."""
        validator = InputValidator()
        
        # Normal text
        assert validator.detect_sql_injection("normal search") == False
        
        # SQL injection attempt
        assert validator.detect_sql_injection("SELECT * FROM users") == True
        assert validator.detect_sql_injection("DROP TABLE users") == True
        assert validator.detect_sql_injection("' OR '1'='1") == True
        
        # Safe SQL-like text in context
        assert validator.detect_sql_injection("I selected this option") == True  # Contains SELECT

    def test_validate_software_name(self):
        """Test software name validation."""
        validator = InputValidator()
        
        # Valid names
        assert validator.validate_software_name("Chrome") == True
        assert validator.validate_software_name("Visual Studio Code") == True
        assert validator.validate_software_name("App-v1.2.3") == True
        
        # Invalid names
        assert validator.validate_software_name("") == False
        assert validator.validate_software_name("A" * 300) == False

    def test_validate_file_type(self):
        """Test file type validation."""
        validator = InputValidator()
        
        # Valid types
        assert validator.validate_file_type("exe") == True
        assert validator.validate_file_type("apk") == True
        assert validator.validate_file_type("zip") == True
        assert validator.validate_file_type("pdf") == True
        
        # Invalid types
        assert validator.validate_file_type("virus") == False
        assert validator.validate_file_type("malware") == False


class TestFloodProtection:
    """Test flood protection."""

    def test_detects_flooding(self):
        """Test flood detection."""
        protection = FloodProtection(max_messages=5, window_seconds=60)
        
        # Send messages within limit
        for _ in range(5):
            assert protection.is_flooding(12345) == False
        
        # 6th message should trigger flood
        assert protection.is_flooding(12345) == True

    def test_warning_system(self):
        """Test warning accumulation."""
        protection = FloodProtection(max_messages=3, window_seconds=60)
        
        # First flood
        for _ in range(4):
            protection.is_flooding(11111)
        
        # Should have 1 warning
        assert protection._warnings[11111] == 1
        
        # Reset and flood again
        for _ in range(4):
            protection.is_flooding(11111)
        
        assert protection._warnings[11111] == 2

    def test_blocking(self):
        """Test that users get blocked after repeated flooding."""
        protection = FloodProtection(max_messages=2, window_seconds=60)
        
        # Flood 3 times to get blocked
        for _ in range(3):
            for _ in range(3):  # Exceed limit
                protection.is_flooding(99999)
        
        # Should be blocked
        assert protection.is_flooding(99999) == True


class TestSecurityManager:
    """Test security manager integration."""

    @pytest.mark.asyncio
    async def test_request_checking(self):
        """Test comprehensive request checking."""
        manager = SecurityManager()
        
        # Normal request
        allowed, reason = await manager.check_request(111111)
        assert allowed == True
        assert reason == "ok"

    def test_input_sanitization(self):
        """Test input sanitization through manager."""
        manager = SecurityManager()
        
        # Clean input
        result = manager.sanitize_input("Hello World")
        assert result == "Hello World"
        
        # Input with SQL injection
        result = manager.sanitize_input("DROP TABLE users")
        assert result == ""  # Blocked

        # Long input
        result = manager.sanitize_input("A" * 1000, max_length=50)
        assert len(result) == 50
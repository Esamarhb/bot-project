"""
Logging configuration module.
Provides advanced logging setup with file rotation and formatting.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional
import json
from datetime import datetime


class CustomFormatter(logging.Formatter):
    """Custom formatter with colored output for console."""

    COLORS = {
        'DEBUG': '\033[36m',     # Cyan
        'INFO': '\033[32m',      # Green
        'WARNING': '\033[33m',   # Yellow
        'ERROR': '\033[31m',     # Red
        'CRITICAL': '\033[35m',  # Magenta
    }
    RESET = '\033[0m'

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors for console."""
        if hasattr(record, 'color') and record.color:
            log_color = self.COLORS.get(record.levelname, self.RESET)
            record.levelname = f"{log_color}{record.levelname}{self.RESET}"
        return super().format(record)


class JSONFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': record.levelname,
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
            'message': record.getMessage(),
        }

        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id

        if record.exc_info and record.exc_info[0]:
            log_data['exception'] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False)


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: str = "INFO",
    enable_json: bool = False
) -> logging.Logger:
    """
    Set up logger with console and file handlers.

    Args:
        name: Logger name
        log_file: Path to log file
        level: Logging level
        enable_json: Enable JSON formatting for file logs

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper()))

    # Remove existing handlers
    logger.handlers.clear()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_formatter = CustomFormatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)

        if enable_json:
            file_formatter = JSONFormatter()
        else:
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - '
                '%(module)s:%(funcName)s:%(lineno)d - %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S'
            )

        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger
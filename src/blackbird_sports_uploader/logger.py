import logging
import sys
from .config import settings


from logging.handlers import RotatingFileHandler

def setup_logging(name: str) -> logging.Logger:
    """
    Setup logging configuration for the application.
    Configures console and rotating file handlers based on settings.
    """
    logger = logging.getLogger(name)
    
    # Set logger to the lowest level to capture all messages
    console_level = settings.LOG_LEVEL_CONSOLE.upper()
    file_level = settings.LOG_LEVEL_FILE.upper()
    
    min_level = min(
        getattr(logging, console_level, logging.INFO),
        getattr(logging, file_level, logging.DEBUG)
    )
    logger.setLevel(min_level)

    # Use a standard format
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    if not logger.handlers:
        # Console Handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(console_level)
        logger.addHandler(console_handler)

        # File Handler (Rotating)
        file_handler = RotatingFileHandler(
            settings.log_file_path,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(file_level)
        logger.addHandler(file_handler)

    return logger

import sys

from loguru import logger

from app.core.config.manager import settings

LOG_FORMAT = (
    '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | '
    '<level>{level: <8}</level> | '
    '<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | '
    '<level>{message}</level>'
)

def configure_logger() -> None:
    """Настраивает логирование в Loguru."""

    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.LOGGING_LEVEL,
        format=LOG_FORMAT,
        backtrace=settings.DEBUG,
        diagnose=settings.DEBUG,
    )

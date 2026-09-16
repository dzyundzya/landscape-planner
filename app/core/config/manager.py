from functools import lru_cache

from app.core.config.settings.base_settings import BackendSettings


@lru_cache
def get_settings() -> BackendSettings:
    """Возвращает настройки приложения."""

    return BackendSettings()


settings = get_settings()

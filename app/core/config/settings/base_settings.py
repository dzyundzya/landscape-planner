from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackendSettings(BaseSettings):
    """Настройки бека приложения."""

    TITLE: str = 'API Landscape-planner'
    VERSION: str = '1.0.0'
    TIMEZONE: str = 'Europe/Moscow'
    DESCRIPTION: str | None = None
    DEBUG: bool = False

    SERVER_HOST: str
    SERVER_PORT: int
    SERVER_WORKERS: int
    API_PREFIX: str = '/api'
    DOCS_URL: str = '/docs'
    OPENAPI_URL: str = '/openapi.json'
    REDOC_URL: str = '/redoc'

    # Postgres
    DB_POSTGRES_HOST: str
    DB_MAX_POOL_CON: int
    DB_POSTGRES_NAME: str
    DB_POSTGRES_PASSWORD: SecretStr
    DB_POOL_SIZE: int
    DB_POOL_OVERFLOW: int
    DB_POSTGRES_PORT: int
    DB_POSTGRES_SCHEMA: str
    DB_TIMEOUT: int
    DB_POSTGRES_USERNAME: str

    IS_DB_ECHO_LOG: bool
    IS_DB_FORCE_ROLLBACK: bool
    IS_DB_EXPIRE_ON_COMMIT: bool = False

    IS_ALLOWED_CREDENTIALS: bool
    ALLOWED_ORIGINS: list[str] = ['*']
    ALLOWED_METHODS: list[str] = ['*']
    ALLOWED_HEADERS: list[str] = ['*']

    LOGGING_LEVEL: str = 'INFO'
    LOGGERS: tuple[str, str] = ('uvicorn.asgi', 'uvicorn.access')

    FILE_STORAGE_ROOT: Path = Path('var/storage')
    MAX_UPLOAD_SIZE_BYTES: int = 50 * 1024 * 1024
    MAX_ARTIFACT_SIZE_BYTES: int = 200 * 1024 * 1024
    NORMATIVE_RULES_PATH: Path = Path('config/normative_rules.yaml')
    PLANT_CATALOG_PATH: Path = Path('config/plant_catalog.yaml')
    GEOMETRY_CURVE_TOLERANCE_M: float = 0.01

    WORKER_ADVISORY_LOCK_ID: int = 1_196_578_126
    WORKER_POLL_INTERVAL_SECONDS: float = 1.0
    WORKER_LOCK_CHECK_INTERVAL_SECONDS: float = 1.0

    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        case_sensitive=True,
        extra='ignore',
    )

    @property
    def database_url(self) -> str:

        return (
            f'postgresql+asyncpg://{self.DB_POSTGRES_USERNAME}:'
            f'{self.DB_POSTGRES_PASSWORD.get_secret_value()}@{self.DB_POSTGRES_HOST}:'
            f'{self.DB_POSTGRES_PORT}/{self.DB_POSTGRES_NAME}'
        )

    @property
    def set_backend_app_attributes(self) -> dict[str, str | bool | None]:

        return {
            'title': self.TITLE,
            'version': self.VERSION,
            'debug': self.DEBUG,
            'description': self.DESCRIPTION,
            'docs_url': self.DOCS_URL,
            'openapi_url': self.OPENAPI_URL,
            'redoc_url': self.REDOC_URL,
        }

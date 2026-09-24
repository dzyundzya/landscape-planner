import sentry_sdk
from loguru import logger
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.loguru import LoggingLevels, LoguruIntegration

from app.core.config.manager import settings

SENTRY_FLUSH_TIMEOUT_SECONDS = 2


def configure_sentry(service_name: str) -> bool:
    """Подключает Sentry при наличии DSN и помечает процесс приложения."""

    dsn = settings.SENTRY_DSN.get_secret_value().strip() if settings.SENTRY_DSN else ''
    if not dsn:
        return False

    integrations = [
        LoguruIntegration(
            level=LoggingLevels.INFO.value,
            event_level=LoggingLevels.ERROR.value,
            sentry_logs_level=LoggingLevels.WARNING.value,
        )
    ]
    if service_name == 'api':
        integrations.append(FastApiIntegration(transaction_style='endpoint'))

    try:
        sentry_sdk.init(
            dsn=dsn,
            environment=settings.SENTRY_ENVIRONMENT,
            release=settings.SENTRY_RELEASE or f'landscape-planner@{settings.VERSION}',
            integrations=integrations,
            auto_enabling_integrations=False,
            enable_logs=settings.SENTRY_ENABLE_LOGS,
            traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
            send_default_pii=False,
            max_request_body_size='never',
        )
        sentry_sdk.get_global_scope().set_tag('service', service_name)
    except Exception:
        logger.exception('Не удалось настроить Sentry: service={}', service_name)
        return False

    logger.info(
        'Sentry подключён: service={}, environment={}, traces_sample_rate={}',
        service_name,
        settings.SENTRY_ENVIRONMENT,
        settings.SENTRY_TRACES_SAMPLE_RATE,
    )
    return True


def flush_sentry() -> None:
    """Отправляет накопленные события перед остановкой процесса."""

    if sentry_sdk.get_client().is_active():
        sentry_sdk.flush(timeout=SENTRY_FLUSH_TIMEOUT_SECONDS)

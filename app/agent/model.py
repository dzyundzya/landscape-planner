from ipaddress import ip_address
from urllib.parse import urlparse

from langchain_openai import ChatOpenAI

from app.core.config.settings.base_settings import BackendSettings
from app.services.exceptions.agents import AgentUnavailableError


def build_chat_model(settings: BackendSettings) -> ChatOpenAI:
    """Создаёт единый OpenAI-compatible адаптер для агента и LLM-планировщика."""

    if not settings.AGENT_ENABLED:
        raise AgentUnavailableError('Агент отключён. Установите AGENT_ENABLED=true')
    provider = (settings.LLM_PROVIDER or '').strip().lower()
    model_name = (settings.LLM_MODEL or '').strip()
    if provider not in {'openai', 'openai_compatible'}:
        raise AgentUnavailableError('Поддерживаются провайдеры openai и openai_compatible')
    if not model_name:
        raise AgentUnavailableError('Не задана модель агента в LLM_MODEL')
    if provider == 'openai_compatible' and not settings.LLM_BASE_URL:
        raise AgentUnavailableError('Для openai_compatible требуется LLM_BASE_URL')
    if _uses_external_provider(settings=settings) and not settings.ALLOW_EXTERNAL_LLM:
        raise AgentUnavailableError('Передача сводок внешнему LLM отключена')

    api_key = settings.LLM_API_KEY.get_secret_value() if settings.LLM_API_KEY else None
    try:
        return ChatOpenAI(
            model=model_name,
            api_key=api_key,
            base_url=settings.LLM_BASE_URL,
            temperature=0,
            timeout=settings.AGENT_TIMEOUT_SECONDS,
            max_retries=1,
        )
    except Exception as exc:
        raise AgentUnavailableError('Не настроен ключ доступа к модели агента') from exc


def _uses_external_provider(settings: BackendSettings) -> bool:
    if not settings.LLM_BASE_URL:
        return True
    hostname = urlparse(settings.LLM_BASE_URL).hostname
    if hostname is None or hostname == 'localhost':
        return False
    try:
        return not ip_address(hostname).is_loopback
    except ValueError:
        return True

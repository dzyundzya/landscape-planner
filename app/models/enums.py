from enum import StrEnum


class ProjectFileFormat(StrEnum):
    """Формат исходного файла проекта."""

    DXF = 'dxf'
    DWF = 'dwf'


class ProjectFileStatus(StrEnum):
    """Готовность исходного файла к анализу."""

    READY = 'ready'
    CONVERSION_REQUIRED = 'conversion_required'


class JobType(StrEnum):
    """Тип фоновой задачи."""

    CONVERT_DWF = 'convert_dwf'
    ANALYZE = 'analyze'
    GENERATE_PLAN = 'generate_plan'
    EXPORT = 'export'
    AGENT_REQUEST = 'agent_request'


class JobStatus(StrEnum):
    """Состояние фоновой задачи."""

    QUEUED = 'queued'
    RUNNING = 'running'
    SUCCEEDED = 'succeeded'
    FAILED = 'failed'

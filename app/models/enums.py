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


class FileArtifactKind(StrEnum):
    """Назначение сформированного файла."""

    CANONICAL_DXF = 'canonical_dxf'
    RESULT_DXF = 'result_dxf'
    PLAN_JSON = 'plan_json'
    REPORT_JSON = 'report_json'
    REPORT_MARKDOWN = 'report_markdown'


class FileArtifactFormat(StrEnum):
    """Формат сформированного файла."""

    DXF = 'dxf'
    JSON = 'json'
    MARKDOWN = 'markdown'

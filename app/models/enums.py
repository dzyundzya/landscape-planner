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


class AnalysisWarningSeverity(StrEnum):
    """Серьёзность предупреждения анализа чертежа."""

    INFO = 'info'
    WARNING = 'warning'
    BLOCKING = 'blocking'


class CoordinateUnit(StrEnum):
    """Подтверждённая единица координат исходного чертежа."""

    MILLIMETER = 'millimeter'
    CENTIMETER = 'centimeter'
    METER = 'meter'
    KILOMETER = 'kilometer'
    INCH = 'inch'
    FOOT = 'foot'
    YARD = 'yard'


class SemanticObjectType(StrEnum):
    """Подтверждённое назначение объектов слоя."""

    BUILDING = 'building'
    ROAD = 'road'
    UTILITY_WATER = 'utility_water'
    UTILITY_SEWER = 'utility_sewer'
    UTILITY_GAS = 'utility_gas'
    UTILITY_POWER = 'utility_power'
    EXISTING_TREE = 'existing_tree'
    EXISTING_BUSH = 'existing_bush'
    OTHER_OBSTACLE = 'other_obstacle'
    IGNORE = 'ignore'


class NormativeRulesStatus(StrEnum):
    """Статус нормативного набора снимка конфигурации."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'


class PlanStatus(StrEnum):
    """Состояние проверки плана озеленения."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'
    INVALID = 'invalid'

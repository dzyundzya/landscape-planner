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
    VALIDATE_PLAN = 'validate_plan'
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


class PlantCatalogStatus(StrEnum):
    """Статус проверки происхождения справочника растений."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'


class TerritoryType(StrEnum):
    """Тип территории для подбора рекомендованного ассортимента."""

    COURTYARD = 'courtyard'
    PRESCHOOL = 'preschool'
    EDUCATION_AND_SPORT = 'education_and_sport'
    HEALTHCARE = 'healthcare'
    ROADS = 'roads'
    PUBLIC_AND_COMMERCIAL = 'public_and_commercial'
    PARKS_AND_PUBLIC_GREEN = 'parks_and_public_green'
    INDUSTRIAL_AND_PROTECTION = 'industrial_and_protection'


class PlanStatus(StrEnum):
    """Состояние проверки плана озеленения."""

    NEEDS_VERIFICATION = 'needs_verification'
    VERIFIED = 'verified'
    INVALID = 'invalid'


class ValidationStatus(StrEnum):
    """Результат отдельной проверки или всего запуска Validator."""

    PASSED = 'passed'
    FAILED = 'failed'
    NEEDS_VERIFICATION = 'needs_verification'


class PlantingType(StrEnum):
    """Тип проектируемой посадки."""

    TREE = 'tree'
    BUSH = 'bush'


class PlantingSource(StrEnum):
    """Источник появления посадки в плане."""

    GENERATED = 'generated'
    MANUAL = 'manual'

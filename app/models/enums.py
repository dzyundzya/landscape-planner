from enum import StrEnum


class ProjectFileFormat(StrEnum):
    """Формат исходного файла проекта."""

    DXF = 'dxf'
    DWF = 'dwf'


class ProjectFileStatus(StrEnum):
    """Готовность исходного файла к анализу."""

    READY = 'ready'
    CONVERSION_REQUIRED = 'conversion_required'

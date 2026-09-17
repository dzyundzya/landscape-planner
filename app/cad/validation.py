from pathlib import Path

import ezdxf
from ezdxf.lldxf.const import DXFError


class InvalidDxfError(Exception):
    """Файл не является читаемым DXF."""


class InvalidDwfError(Exception):
    """Файл не содержит заголовок DWF."""


def validate_dxf(path: Path) -> None:
    """Проверяет возможность чтения DXF без изменения документа."""

    try:
        ezdxf.readfile(path)
    except (DXFError, OSError, UnicodeError) as exc:
        raise InvalidDxfError from exc


def validate_dwf(path: Path) -> None:
    """Проверяет обязательную сигнатуру контейнера DWF."""

    try:
        with path.open('rb') as source:
            signature = source.read(6)
    except OSError as exc:
        raise InvalidDwfError from exc

    if signature != b'(DWF V':
        raise InvalidDwfError

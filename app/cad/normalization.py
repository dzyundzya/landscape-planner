import math
from collections.abc import Iterable
from functools import partial
from pathlib import Path

import ezdxf
from ezdxf.document import Drawing
from ezdxf.entities import DXFEntity, Insert
from ezdxf.lldxf.const import DXFError
from ezdxf.path import make_path

from app.domain import (
    GeometryProvenance,
    NormalizationIssue,
    NormalizationOptions,
    NormalizationResult,
    NormalizedPolyline,
    Point2D,
)

GEOMETRY_ENTITY_TYPES = frozenset({'ARC', 'CIRCLE', 'LINE', 'LWPOLYLINE', 'POLYLINE'})
NON_GEOMETRY_ENTITY_TYPES = frozenset({'ATTDEF', 'ATTRIB', 'MTEXT', 'TEXT'})


class DxfNormalizationError(Exception):
    """DXF не удалось безопасно открыть для нормализации."""


class DxfGeometryNormalizer:
    """Преобразует поддерживаемые modelspace-объекты в плоские DTO."""

    def __init__(self, options: NormalizationOptions) -> None:
        self.options = options
        self._geometries: list[NormalizedPolyline] = []
        self._issues: list[NormalizationIssue] = []

    def normalize(self, document: Drawing) -> NormalizationResult:
        """Нормализует modelspace одного DXF-документа."""

        self._geometries = []
        self._issues = []
        self._walk_entities(
            entities=document.modelspace(),
            insert_path=(),
            inherited_layer=None,
            active_blocks=(),
            depth=0,
        )
        return NormalizationResult(
            geometries=tuple(self._geometries),
            issues=tuple(self._issues),
        )

    def _walk_entities(
        self,
        entities: Iterable[DXFEntity],
        insert_path: tuple[str, ...],
        inherited_layer: str | None,
        active_blocks: tuple[str, ...],
        depth: int,
    ) -> None:
        for ordinal, entity in enumerate(entities):
            effective_layer = self._effective_layer(entity=entity, inherited_layer=inherited_layer)
            if isinstance(entity, Insert):
                self._walk_insert(
                    insert=entity,
                    insert_path=insert_path,
                    effective_layer=effective_layer,
                    active_blocks=active_blocks,
                    depth=depth,
                    ordinal=ordinal,
                )
                continue

            source_object_id, handle = self._get_source_identity(
                entity=entity,
                insert_path=insert_path,
                ordinal=ordinal,
            )
            entity_type = entity.dxftype()
            if entity_type in GEOMETRY_ENTITY_TYPES:
                self._normalize_geometry(
                    entity=entity,
                    effective_layer=effective_layer,
                    insert_path=insert_path,
                    source_object_id=source_object_id,
                    handle=handle,
                )
            elif entity_type not in NON_GEOMETRY_ENTITY_TYPES:
                self._issues.append(
                    NormalizationIssue(
                        code='unsupported_entity',
                        message=f'Entity type {entity_type} is not supported by geometry normalization',
                        source_object_id=source_object_id,
                    )
                )

    def _walk_insert(
        self,
        insert: Insert,
        insert_path: tuple[str, ...],
        effective_layer: str,
        active_blocks: tuple[str, ...],
        depth: int,
        ordinal: int,
    ) -> None:
        block_name = insert.dxf.get('name', '')
        source_object_id, handle = self._get_source_identity(insert, insert_path, ordinal)
        if depth >= self.options.max_insert_depth:
            self._issues.append(
                NormalizationIssue(
                    code='insert_depth_exceeded',
                    message=f'INSERT nesting exceeds {self.options.max_insert_depth} levels',
                    source_object_id=source_object_id,
                )
            )
            return
        if block_name in active_blocks:
            self._issues.append(
                NormalizationIssue(
                    code='cyclic_insert',
                    message=f'Cyclic INSERT reference detected for block {block_name}',
                    source_object_id=source_object_id,
                )
            )
            return

        inserts = tuple(insert.multi_insert()) if insert.mcount > 1 else (insert,)
        for index, resolved_insert in enumerate(inserts):
            segment = self._insert_segment(block_name=block_name, handle=handle, index=index, count=len(inserts))
            child_path = (*insert_path, segment)
            skipped: list[tuple[DXFEntity, str]] = []

            try:
                virtual_entities = tuple(
                    resolved_insert.virtual_entities(skipped_entity_callback=partial(_record_skipped, skipped))
                )
            except (DXFError, ValueError, ArithmeticError, TypeError) as exc:
                self._issues.append(
                    NormalizationIssue(
                        code='insert_transformation_failed',
                        message=f'INSERT transformation failed: {exc.__class__.__name__}',
                        source_object_id=source_object_id,
                    )
                )
                continue

            for skipped_entity, reason in skipped:
                skipped_id, _ = self._get_source_identity(skipped_entity, child_path, 0)
                self._issues.append(
                    NormalizationIssue(
                        code='insert_entity_skipped',
                        message=f'INSERT entity transformation was skipped: {reason}',
                        source_object_id=skipped_id,
                    )
                )
            self._walk_entities(
                entities=virtual_entities,
                insert_path=child_path,
                inherited_layer=effective_layer,
                active_blocks=(*active_blocks, block_name),
                depth=depth + 1,
            )

    def _normalize_geometry(
        self,
        entity: DXFEntity,
        effective_layer: str,
        insert_path: tuple[str, ...],
        source_object_id: str,
        handle: str | None,
    ) -> None:
        try:
            path = make_path(entity)
            vertices = tuple(path.flattening(distance=self.options.curve_tolerance, segments=4))
        except (DXFError, ValueError, ArithmeticError, TypeError, NotImplementedError) as exc:
            self._issues.append(
                NormalizationIssue(
                    code='geometry_conversion_failed',
                    message=f'Geometry conversion failed: {exc.__class__.__name__}',
                    source_object_id=source_object_id,
                )
            )
            return

        if len(vertices) < 2 or any(not all(math.isfinite(value) for value in vertex.xyz) for vertex in vertices):
            self._issues.append(
                NormalizationIssue(
                    code='invalid_geometry_coordinates',
                    message='Geometry has insufficient or non-finite coordinates',
                    source_object_id=source_object_id,
                )
            )
            return

        z_values = [vertex.z for vertex in vertices]
        original = entity.source_of_copy or entity
        self._geometries.append(
            NormalizedPolyline(
                points=tuple(Point2D(x=vertex.x, y=vertex.y) for vertex in vertices),
                closed=path.is_closed,
                provenance=GeometryProvenance(
                    source_object_id=source_object_id,
                    handle=handle,
                    entity_type=original.dxftype(),
                    layer=effective_layer,
                    source_layer=original.dxf.get('layer', '0'),
                    insert_path=insert_path,
                    min_z=min(z_values),
                    max_z=max(z_values),
                ),
            )
        )

    @staticmethod
    def _effective_layer(entity: DXFEntity, inherited_layer: str | None) -> str:
        layer = entity.dxf.get('layer', '0')
        if layer == '0' and inherited_layer is not None:
            return inherited_layer
        return layer

    @staticmethod
    def _get_source_identity(
        entity: DXFEntity,
        insert_path: tuple[str, ...],
        ordinal: int,
    ) -> tuple[str, str | None]:
        original = entity.source_of_copy or entity
        handle = original.dxf.get('handle')
        local_id = f'{original.dxftype()}:{handle or ordinal}'
        return '/'.join((*insert_path, local_id)), handle

    @staticmethod
    def _insert_segment(block_name: str, handle: str | None, index: int, count: int) -> str:
        segment = f'INSERT:{block_name}:{handle or "virtual"}'
        if count > 1:
            return f'{segment}[{index}]'
        return segment


def normalize_dxf(path: Path, options: NormalizationOptions) -> NormalizationResult:
    """Читает DXF и нормализует поддерживаемую геометрию modelspace."""

    try:
        document = ezdxf.readfile(path)
    except (DXFError, OSError, UnicodeError) as exc:
        raise DxfNormalizationError('Не удалось прочитать исходный DXF') from exc
    return DxfGeometryNormalizer(options=options).normalize(document=document)


def _record_skipped(target: list[tuple[DXFEntity, str]], entity: DXFEntity, reason: str) -> None:
    target.append((entity, reason))

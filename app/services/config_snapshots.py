import hashlib
import json
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config.manager import settings
from app.models import ConfigSnapshotModel, CoordinateUnit, NormativeRulesStatus
from app.planning import PlantingValidationError
from app.planning.planting_validation import build_boundary
from app.repositories.crud.analyses import AnalysisCRUDRepository
from app.repositories.crud.config_snapshots import ConfigSnapshotCRUDRepository
from app.repositories.crud.project_files import ProjectFileCRUDRepository
from app.repositories.crud.projects import ProjectCRUDRepository
from app.rules import LoadedRuleSet, RuleCatalogError, RuleVerificationStatus, load_rule_set
from app.schemas.config_snapshot import ConfigSnapshotUpsertSchema
from app.services.base import BaseService
from app.services.exceptions.config_snapshots import ConfigPrerequisiteError, InvalidConfigSnapshotError
from app.services.exceptions.projects import ProjectNotFoundError

CONFIG_SCHEMA_VERSION = 1
UNIT_SCALE_TO_METERS = {
    CoordinateUnit.MILLIMETER: Decimal('0.001'),
    CoordinateUnit.CENTIMETER: Decimal('0.01'),
    CoordinateUnit.METER: Decimal('1'),
    CoordinateUnit.KILOMETER: Decimal('1000'),
    CoordinateUnit.INCH: Decimal('0.0254'),
    CoordinateUnit.FOOT: Decimal('0.3048'),
    CoordinateUnit.YARD: Decimal('0.9144'),
}


class ConfigSnapshotService(BaseService[ConfigSnapshotCRUDRepository]):
    """Бизнес-логика подтверждённых настроек проекта."""

    repository_class = ConfigSnapshotCRUDRepository

    def __init__(self, async_session: AsyncSession) -> None:
        super().__init__(async_session=async_session)
        self.project_repository = ProjectCRUDRepository(async_session=async_session)
        self.project_file_repository = ProjectFileCRUDRepository(async_session=async_session)
        self.analysis_repository = AnalysisCRUDRepository(async_session=async_session)

    async def save_current_config(
        self,
        project_id: int,
        data: ConfigSnapshotUpsertSchema,
    ) -> ConfigSnapshotModel:
        """Создаёт новый снимок настроек текущего анализа или возвращает идентичный."""

        if await self.project_repository.get_project_by_id_for_update(project_id=project_id) is None:
            raise ProjectNotFoundError(project_id=project_id)

        project_file = await self.project_file_repository.get_latest_for_project(project_id=project_id)
        if project_file is None:
            raise ConfigPrerequisiteError(f'У проекта с id={project_id} отсутствует исходный файл')

        analysis = await self.analysis_repository.get_latest_for_project_file(project_file_id=project_file.id)
        if analysis is None:
            raise ConfigPrerequisiteError(f'У проекта с id={project_id} отсутствует анализ текущего исходного файла')

        self._validate_boundary(data=data)
        self._validate_layer_mappings(data=data, analysis_result=analysis.result)
        rule_set = self._load_rule_set()
        rules_status = self._get_rules_status(rule_set=rule_set)
        scale = UNIT_SCALE_TO_METERS[data.coordinate_unit]
        payload = self._build_payload(
            analysis_id=analysis.id,
            data=data,
            scale=scale,
            rule_set=rule_set,
            rules_status=rules_status,
        )
        content_sha256 = self._calculate_hash(payload=payload)

        existing_snapshot = await self.repository.get_by_content_hash(
            project_id=project_id,
            content_sha256=content_sha256,
        )
        if existing_snapshot is not None:
            return existing_snapshot

        snapshot = await self.repository.create_obj(
            new_obj=ConfigSnapshotModel(
                project_id=project_id,
                analysis_id=analysis.id,
                version=await self.repository.get_next_version(project_id=project_id),
                schema_version=CONFIG_SCHEMA_VERSION,
                coordinate_unit=data.coordinate_unit,
                unit_scale_to_meters=scale,
                boundary=data.boundary.model_dump(mode='json'),
                layer_mappings=[mapping.model_dump(mode='json') for mapping in data.layer_mappings],
                generation=data.generation.model_dump(mode='json'),
                rules_status=rules_status,
                rules_version=rule_set.data.version,
                rules_sha256=rule_set.sha256,
                content_sha256=content_sha256,
            )
        )
        await self.session.commit()

        logger.info(
            'Настройки проекта сохранены: config_id={}, project_id={}, analysis_id={}, version={}',
            snapshot.id,
            project_id,
            analysis.id,
            snapshot.version,
        )
        return snapshot

    @staticmethod
    def _validate_boundary(data: ConfigSnapshotUpsertSchema) -> None:
        try:
            build_boundary(boundary=data.boundary.model_dump(mode='json'))
        except PlantingValidationError as exc:
            raise InvalidConfigSnapshotError(str(exc)) from exc

    @staticmethod
    def _validate_layer_mappings(data: ConfigSnapshotUpsertSchema, analysis_result: dict[str, object]) -> None:
        analysis_layers = {
            str(layer.get('name', '')).casefold()
            for layer in analysis_result.get('layers', [])
            if isinstance(layer, dict)
        }
        unknown_layers = [
            mapping.layer for mapping in data.layer_mappings if mapping.layer.casefold() not in analysis_layers
        ]
        if unknown_layers:
            raise InvalidConfigSnapshotError(f'Mapping ссылается на неизвестные слои: {", ".join(unknown_layers)}')

    @staticmethod
    def _build_payload(
        analysis_id: int,
        data: ConfigSnapshotUpsertSchema,
        scale: Decimal,
        rule_set: LoadedRuleSet,
        rules_status: NormativeRulesStatus,
    ) -> dict[str, object]:
        return {
            'analysis_id': analysis_id,
            'schema_version': CONFIG_SCHEMA_VERSION,
            'coordinate_unit': data.coordinate_unit.value,
            'unit_scale_to_meters': str(scale),
            'boundary': data.boundary.model_dump(mode='json'),
            'layer_mappings': [mapping.model_dump(mode='json') for mapping in data.layer_mappings],
            'generation': data.generation.model_dump(mode='json'),
            'rules_status': rules_status.value,
            'rules_version': rule_set.data.version,
            'rules_sha256': rule_set.sha256,
        }

    @staticmethod
    def _load_rule_set() -> LoadedRuleSet:
        try:
            return load_rule_set(settings.NORMATIVE_RULES_PATH)
        except RuleCatalogError as exc:
            raise InvalidConfigSnapshotError('Не удалось зафиксировать нормативный справочник') from exc

    @staticmethod
    def _get_rules_status(rule_set: LoadedRuleSet) -> NormativeRulesStatus:
        if rule_set.data.rules and all(
            rule.verification_status is RuleVerificationStatus.VERIFIED for rule in rule_set.data.rules
        ):
            return NormativeRulesStatus.VERIFIED
        return NormativeRulesStatus.NEEDS_VERIFICATION

    @staticmethod
    def _calculate_hash(payload: dict[str, object]) -> str:
        canonical_json = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical_json.encode()).hexdigest()

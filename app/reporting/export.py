import json
from dataclasses import dataclass

from app.cad import EXPORT_DXF_VERSION, DxfExportMetadata
from app.schemas.export import ExportJobInputSchema

REPORT_SCHEMA_VERSION = 1
REPORT_LIMITATIONS = (
    'Расчёт выполнен в 2D по подтверждённой классификации объектов исходного DXF.',
    'Символы растений в DXF являются условными обозначениями и не показывают размер кроны.',
)


@dataclass(frozen=True, slots=True)
class ExportDocuments:
    """Сериализованные документы одной экспортируемой ревизии."""

    plan_json: bytes
    report_json: bytes
    report_markdown: bytes
    draft: bool


def build_export_documents(
    project_id: int,
    job_input: ExportJobInputSchema,
    dxf_metadata: DxfExportMetadata,
) -> ExportDocuments:
    """Строит план и отчёты только из зафиксированных проверенных фактов."""

    plan = {
        'schema_version': 1,
        'export_version': EXPORT_DXF_VERSION,
        'export_status': 'draft' if job_input.draft else 'verified',
        'disclaimer': _draft_disclaimer(job_input),
        'project_id': project_id,
        'plan_id': job_input.plan_id,
        'plan_revision': job_input.plan_revision,
        'project_file_id': job_input.project_file_id,
        'project_file_sha256': job_input.project_file_sha256,
        'config_snapshot_id': job_input.config_snapshot_id,
        'config_content_sha256': job_input.config.content_sha256,
        'coordinate_space': 'local_meters',
        'generator_version': job_input.plan.generator_version,
        'generation_summary': job_input.plan.generation_summary.model_dump(mode='json'),
        'plantings': [planting.model_dump(mode='json') for planting in job_input.plan.plantings],
        'dxf_layers': dxf_metadata.layers,
        'dxf_blocks': {planting_type.value: name for planting_type, name in dxf_metadata.blocks.items()},
    }
    report = {
        'schema_version': REPORT_SCHEMA_VERSION,
        'export_version': EXPORT_DXF_VERSION,
        'export_status': 'draft' if job_input.draft else 'verified',
        'disclaimer': _draft_disclaimer(job_input),
        'project_id': project_id,
        'plan_id': job_input.plan_id,
        'plan_revision': job_input.plan_revision,
        'validation_id': job_input.validation.id,
        'status': job_input.validation.status.value,
        'validator_version': job_input.validation.validator_version,
        'summary': job_input.validation.summary.model_dump(mode='json'),
        'provenance': {
            'project_file_sha256': job_input.project_file_sha256,
            'config_content_sha256': job_input.config.content_sha256,
            'rules_status': job_input.config.rules_status.value,
            'rules_version': job_input.config.rules_version,
            'rules_sha256': job_input.config.rules_sha256,
            'plant_catalog_status': job_input.config.plant_catalog_status.value,
            'plant_catalog_version': job_input.config.plant_catalog_version,
            'plant_catalog_sha256': job_input.config.plant_catalog_sha256,
        },
        'checks': [check.model_dump(mode='json') for check in job_input.validation.checks],
        'limitations': [*([_draft_disclaimer(job_input)] if job_input.draft else []), *REPORT_LIMITATIONS],
    }
    return ExportDocuments(
        plan_json=_json_bytes(plan),
        report_json=_json_bytes(report),
        report_markdown=_build_markdown(job_input=job_input, report=report).encode('utf-8'),
        draft=job_input.draft,
    )


def _build_markdown(job_input: ExportJobInputSchema, report: dict[str, object]) -> str:
    summary = job_input.validation.summary
    lines = [
        '# Отчёт о проверке плана озеленения',
        '',
        *(
            ['> **ДЕМОНСТРАЦИОННЫЙ ЧЕРНОВИК.** Нормативные правила требуют подтверждения.', '']
            if job_input.draft
            else []
        ),
        f'- Проект: `{report["project_id"]}`',
        f'- План: `{job_input.plan_id}`',
        f'- Ревизия: `{job_input.plan_revision}`',
        f'- Статус: `{job_input.validation.status.value}`',
        f'- Валидатор: `{job_input.validation.validator_version}`',
        '',
        '## Сводка',
        '',
        '| Всего | Пройдено | Нарушено | Требует проверки |',
        '|---:|---:|---:|---:|',
        f'| {summary.total} | {summary.passed} | {summary.failed} | {summary.needs_verification} |',
        '',
        '## Происхождение данных',
        '',
        f'- SHA-256 исходного DXF: `{job_input.project_file_sha256}`',
        f'- SHA-256 конфигурации: `{job_input.config.content_sha256}`',
        f'- Нормативный набор: `{job_input.config.rules_version}` (`{job_input.config.rules_sha256}`)',
        f'- Справочник растений: `{job_input.config.plant_catalog_version}` '
        f'(`{job_input.config.plant_catalog_sha256}`)',
        '',
        '## Проверки',
        '',
        '| Посадка | Проверка | Статус | Факт | Требование | Документ | Пункт | Причина |',
        '|---|---|---|---:|---:|---|---|---|',
    ]
    for check in job_input.validation.checks:
        actual = f'{check.actual} {check.unit}' if check.actual is not None else '—'
        required = f'{check.required} {check.unit}' if check.required is not None else '—'
        lines.append(
            '| {planting} | {check_type} | {status} | {actual} | {required} | {document} | {clause} | {reason} |'.format(
                planting=_escape_markdown(str(check.planting_id) if check.planting_id else '—'),
                check_type=_escape_markdown(check.check_type),
                status=check.status.value,
                actual=_escape_markdown(actual),
                required=_escape_markdown(required),
                document=_escape_markdown(check.document or '—'),
                clause=_escape_markdown(check.clause or '—'),
                reason=_escape_markdown(check.reason),
            )
        )
    lines.extend(
        [
            '',
            '## Ограничения результата',
            '',
            *[f'- {limitation}' for limitation in REPORT_LIMITATIONS],
            '',
        ]
    )
    return '\n'.join(lines)


def _draft_disclaimer(job_input: ExportJobInputSchema) -> str | None:
    if not job_input.draft:
        return None
    return 'Демонстрационный черновик. Нормативные правила требуют подтверждения.'


def _json_bytes(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def _escape_markdown(value: str) -> str:
    return value.replace('|', '\\|').replace('\r', ' ').replace('\n', '<br>')

import { FormEvent, useCallback, useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import {
  addPlanting,
  artifactDownloadUrl,
  deletePlanting,
  getExport,
  getJob,
  getPlan,
  getPlanPreview,
  getPlanReport,
  startExport,
  startPlanGeneration,
  startPlanValidation,
  updatePlanting,
} from '../api'
import type { Job, Plan, PlanExport, PlanValidation, Planting, PlantingType } from '../types'
import { PlanMap } from './PlanMap'

type Props = {
  projectId: number
  initialPlanId: number | null
  onProgress: (progress: { plan: Plan | null; validation: PlanValidation | null; exported: boolean }) => void
}

export function PlanWorkspace({ projectId, initialPlanId, onProgress }: Props) {
  const queryClient = useQueryClient()
  const [generationJob, setGenerationJob] = useState<Job | null>(null)
  const [validationJob, setValidationJob] = useState<Job | null>(null)
  const [exportJob, setExportJob] = useState<Job | null>(null)
  const [selectedPlantingId, setSelectedPlantingId] = useState<string | null>(null)

  const generationMutation = useMutation({
    mutationFn: () => startPlanGeneration(projectId),
    onSuccess: setGenerationJob,
  })
  const generationJobQuery = useJobPolling(generationJob, setGenerationJob)
  const planId = numberFromJob(generationJobQuery.data ?? generationJob, 'plan_id') ?? initialPlanId
  const planQuery = useQuery({
    queryKey: ['plan', projectId, planId],
    queryFn: () => getPlan(projectId, planId!),
    enabled: planId !== null,
  })
  const previewQuery = useQuery({
    queryKey: ['plan-preview', projectId, planId, planQuery.data?.revision],
    queryFn: () => getPlanPreview(projectId, planId!),
    enabled: planId !== null && planQuery.data !== undefined,
  })
  const reportQuery = useQuery({
    queryKey: ['plan-report', projectId, planId, planQuery.data?.revision],
    queryFn: () => getPlanReport(projectId, planId!),
    enabled: planId !== null && planQuery.data !== undefined,
    retry: false,
  })

  const refreshPlan = useCallback(async () => {
    if (planId === null) return
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['plan', projectId, planId] }),
      queryClient.invalidateQueries({ queryKey: ['plan-preview', projectId, planId] }),
      queryClient.invalidateQueries({ queryKey: ['plan-report', projectId, planId] }),
    ])
  }, [planId, projectId, queryClient])

  const updateMutation = useMutation({
    mutationFn: ({ plantingId, revision, payload }: {
      plantingId: string
      revision: number
      payload: { type?: PlantingType; x_m?: number; y_m?: number; species?: string | null }
    }) => updatePlanting(projectId, planId!, plantingId, revision, payload),
    onSuccess: refreshPlan,
    onError: refreshPlan,
  })
  const addMutation = useMutation({
    mutationFn: ({ revision, payload }: {
      revision: number
      payload: { type: PlantingType; x_m: number; y_m: number; species: string | null }
    }) => addPlanting(projectId, planId!, revision, payload),
    onSuccess: async (result) => {
      setSelectedPlantingId(result.planting.public_id)
      await refreshPlan()
    },
    onError: refreshPlan,
  })
  const deleteMutation = useMutation({
    mutationFn: ({ plantingId, revision }: { plantingId: string; revision: number }) =>
      deletePlanting(projectId, planId!, plantingId, revision),
    onSuccess: async () => {
      setSelectedPlantingId(null)
      await refreshPlan()
    },
  })
  const validationMutation = useMutation({
    mutationFn: (plan: Plan) => startPlanValidation(projectId, plan.id, plan.revision),
    onSuccess: setValidationJob,
  })
  const validationJobQuery = useJobPolling(validationJob, setValidationJob)
  useEffect(() => {
    if (validationJobQuery.data?.status === 'succeeded') void refreshPlan()
  }, [refreshPlan, validationJobQuery.data?.status])

  const exportMutation = useMutation({
    mutationFn: (plan: Plan) => startExport(projectId, plan.id, plan.revision),
    onSuccess: setExportJob,
  })
  const exportJobQuery = useJobPolling(exportJob, setExportJob)
  const exportId = numberFromJob(exportJobQuery.data ?? exportJob, 'export_id')
  const exportQuery = useQuery({
    queryKey: ['plan-export', projectId, planId, exportId],
    queryFn: () => getExport(projectId, planId!, exportId!),
    enabled: planId !== null && exportId !== null,
  })

  const plan = planQuery.data ?? null
  const validation: PlanValidation | null = reportQuery.data && reportQuery.data.plan_revision === plan?.revision
    ? reportQuery.data
    : null
  const currentExport = exportQuery.data && exportQuery.data.plan_revision === plan?.revision
    ? exportQuery.data
    : null
  useEffect(() => {
    onProgress({ plan, validation, exported: currentExport !== null })
  }, [currentExport, onProgress, plan, validation])

  const selectedPlanting = useMemo(
    () => plan?.plantings.find((planting) => planting.public_id === selectedPlantingId) ?? null,
    [plan, selectedPlantingId],
  )
  const actionError = generationMutation.error ?? generationJobQuery.error ?? planQuery.error ?? previewQuery.error
    ?? addMutation.error ?? updateMutation.error ?? deleteMutation.error ?? validationMutation.error ?? validationJobQuery.error
    ?? exportMutation.error ?? exportJobQuery.error ?? exportQuery.error

  const movePlanting = useCallback((plantingId: string, x: number, y: number) => {
    if (!plan || updateMutation.isLoading) return
    updateMutation.mutate({ plantingId, revision: plan.revision, payload: { x_m: x, y_m: y } })
  }, [plan, updateMutation])

  if (!generationJob && initialPlanId === null) {
    return (
      <section className="panel action-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">Шаг 5</p><h2>Сгенерируйте план</h2><p className="section-description">Worker построит нормативные зоны, расставит деревья и кустарники и независимо проверит результат.</p></div>
          <button className="button button-primary" type="button" disabled={generationMutation.isLoading} onClick={() => generationMutation.mutate()}>
            {generationMutation.isLoading ? 'Ставим в очередь…' : 'Запустить генерацию'}
          </button>
        </div>
        {generationMutation.error !== null && <InlineError error={generationMutation.error} />}
      </section>
    )
  }

  if (!plan) {
    if (!generationJob) {
      return <section className="panel action-panel"><div className="map-placeholder"><span className="spinner" /> Восстанавливаем план…</div></section>
    }
    return (
      <JobPanel
        eyebrow="Шаг 5"
        title="Генерация плана"
        job={generationJobQuery.data ?? generationJob}
        error={actionError}
        isRetrying={generationMutation.isLoading}
        onRetry={() => generationMutation.mutate()}
      />
    )
  }

  return (
    <>
      <section className="panel plan-panel">
        <div className="panel-heading">
          <div><p className="eyebrow">Шаг 5</p><h2>План озеленения</h2><p className="section-description">План #{plan.id}, ревизия {plan.revision}. Выберите посадку на карте или в списке для редактирования.</p></div>
          <span className={`status-pill validation-${plan.status}`}>{planStatusLabel(plan.status)}</span>
        </div>
        <div className="plan-metrics">
          <Metric label="Деревьев" value={plan.generation_summary.tree_count} />
          <Metric label="Кустарников" value={plan.generation_summary.bush_count} />
          <Metric label="Кандидатов" value={plan.generation_summary.candidate_count} />
          <Metric label="Отклонено" value={plan.generation_summary.rejected_candidate_count} />
        </div>
        {previewQuery.data ? (
          <div className="plan-layout">
            <PlanMap
              preview={previewQuery.data}
              selectedPlantingId={selectedPlantingId}
              onSelectPlanting={setSelectedPlantingId}
              onMovePlanting={movePlanting}
            />
            <PlantingInspector
              planting={selectedPlanting}
              plan={plan}
              isSaving={addMutation.isLoading || updateMutation.isLoading || deleteMutation.isLoading}
              onSelect={setSelectedPlantingId}
              onAdd={(payload) => addMutation.mutate({ revision: plan.revision, payload })}
              onSave={(plantingId, payload) => updateMutation.mutate({ plantingId, revision: plan.revision, payload })}
              onDelete={(plantingId) => deleteMutation.mutate({ plantingId, revision: plan.revision })}
            />
          </div>
        ) : (
          <div className="map-placeholder"><span className="spinner" /> Загружаем геометрию плана…</div>
        )}
        {previewQuery.data && previewQuery.data.issues.length > 0 && (
          <div className="warning-stack compact-warnings">
            {previewQuery.data.issues.map((issue, index) => <article className="notice notice-warning" key={`${issue.code}-${index}`}><span className="notice-marker" /><div><strong>{issue.code}</strong><p>{issue.message}</p></div></article>)}
          </div>
        )}
        {actionError !== null && <InlineError error={actionError} />}
      </section>

      <ValidationPanel
        plan={plan}
        validation={validation}
        job={validationJobQuery.data ?? validationJob}
        isStarting={validationMutation.isLoading}
        onStart={() => validationMutation.mutate(plan)}
      />
      <ExportPanel
        projectId={projectId}
        plan={plan}
        validation={validation}
        job={exportJobQuery.data ?? exportJob}
        exported={currentExport}
        isStarting={exportMutation.isLoading}
        onStart={() => exportMutation.mutate(plan)}
      />
    </>
  )
}

function useJobPolling(job: Job | null, onUpdate: (job: Job) => void) {
  return useQuery<Job>({
    queryKey: ['job', job?.id],
    queryFn: () => getJob(job!.id),
    enabled: job !== null,
    initialData: job ?? undefined,
    refetchInterval: (current) => current && ['queued', 'running'].includes(current.status) ? 1000 : false,
    onSuccess: onUpdate,
  })
}

function PlantingInspector({ planting, plan, isSaving, onSelect, onAdd, onSave, onDelete }: {
  planting: Planting | null
  plan: Plan
  isSaving: boolean
  onSelect: (id: string | null) => void
  onAdd: (payload: { type: PlantingType; x_m: number; y_m: number; species: string | null }) => void
  onSave: (id: string, payload: { type: PlantingType; x_m: number; y_m: number; species: string | null }) => void
  onDelete: (id: string) => void
}) {
  const [type, setType] = useState<PlantingType>('tree')
  const [x, setX] = useState(0)
  const [y, setY] = useState(0)
  const [species, setSpecies] = useState('')
  const [isAdding, setIsAdding] = useState(false)

  useEffect(() => {
    if (!planting) return
    setType(planting.type)
    setX(Number(planting.x_m))
    setY(Number(planting.y_m))
    setSpecies(planting.species ?? '')
  }, [planting])

  function submit(event: FormEvent) {
    event.preventDefault()
    const payload = { type, x_m: x, y_m: y, species: species.trim() || null }
    if (planting) {
      onSave(planting.public_id, payload)
    } else if (isAdding) {
      onAdd(payload)
      setIsAdding(false)
    }
  }

  function startAdding() {
    setType('tree')
    setX(0)
    setY(0)
    setSpecies('')
    setIsAdding(true)
  }

  return (
    <aside className="planting-inspector">
      <div className="inspector-heading"><div><span>Посадки</span><strong>{plan.plantings.length}</strong></div>{planting || isAdding ? <button type="button" className="text-button" onClick={() => { onSelect(null); setIsAdding(false) }}>К списку</button> : <button type="button" className="text-button" onClick={startAdding}>+ Добавить</button>}</div>
      {!planting && !isAdding ? (
        <div className="planting-list">
          {plan.plantings.length === 0 && <p className="empty-list">В плане пока нет посадок.</p>}
          {plan.plantings.slice(0, 100).map((item) => <button type="button" key={item.public_id} onClick={() => onSelect(item.public_id)}><i className={item.type} /><span><strong>{item.species ?? plantingTypeLabel(item.type)}</strong><small>{formatMeters(item.x_m)} · {formatMeters(item.y_m)}</small></span></button>)}
        </div>
      ) : (
        <form className="inspector-form" onSubmit={submit}>
          <p className="planting-id">{planting ? planting.public_id : 'Новая посадка'}</p>
          <label><span>Тип</span><select value={type} onChange={(event) => setType(event.target.value as PlantingType)}><option value="tree">Дерево</option><option value="bush">Кустарник</option></select></label>
          <div className="coordinate-fields"><label><span>X, м</span><input type="number" step="0.001" value={x} onChange={(event) => setX(event.target.valueAsNumber)} /></label><label><span>Y, м</span><input type="number" step="0.001" value={y} onChange={(event) => setY(event.target.valueAsNumber)} /></label></div>
          <label><span>Порода</span><input value={species} placeholder="Не выбрана" onChange={(event) => setSpecies(event.target.value)} /></label>
          <div className={`inspector-actions ${planting ? '' : 'single-action'}`}><button className="button button-primary" disabled={isSaving}>{planting ? 'Сохранить' : 'Добавить'}</button>{planting && <button className="button button-danger" type="button" disabled={isSaving} onClick={() => onDelete(planting.public_id)}>Удалить</button>}</div>
        </form>
      )}
    </aside>
  )
}

function ValidationPanel({ plan, validation, job, isStarting, onStart }: { plan: Plan; validation: PlanValidation | null; job: Job | null; isStarting: boolean; onStart: () => void }) {
  const jobIsActive = job?.status === 'queued' || job?.status === 'running'
  return (
    <section className="panel validation-panel">
      <div className="panel-heading"><div><p className="eyebrow">Шаг 6</p><h2>Проверка и объяснения</h2></div>{validation ? <span className={`status-pill validation-${validation.status}`}>{validationStatusLabel(validation.status)}</span> : <button className="button button-primary" type="button" disabled={isStarting || jobIsActive} onClick={onStart}>{jobIsActive ? 'Проверяем…' : 'Проверить ревизию'}</button>}</div>
      {validation ? (
        <><div className="validation-summary"><Metric label="Всего" value={validation.summary.total} /><Metric label="Пройдено" value={validation.summary.passed} /><Metric label="Нарушено" value={validation.summary.failed} /><Metric label="Требует проверки" value={validation.summary.needs_verification} /></div><div className="check-list">{validation.checks.map((check, index) => <article className={`check-row check-${check.status}`} key={`${check.check_type}-${check.planting_id}-${index}`}><span>{check.status === 'passed' ? '✓' : check.status === 'failed' ? '×' : '?'}</span><div><strong>{check.reason}</strong><small>{check.actual !== null ? `Фактически ${check.actual} ${check.unit}, требуется ${check.required} ${check.unit}` : check.check_type}{check.document ? ` · ${check.document}${check.clause ? `, ${check.clause}` : ''}` : ''}</small></div></article>)}</div></>
      ) : job?.status === 'failed' ? <InlineError error={new Error(job.error ?? 'Повторная проверка завершилась с ошибкой')} /> : <p className="muted">После изменений ревизию нужно проверить повторно. Только успешно проверенный план можно экспортировать.</p>}
    </section>
  )
}

function ExportPanel({ projectId, plan, validation, job, exported, isStarting, onStart }: { projectId: number; plan: Plan; validation: PlanValidation | null; job: Job | null; exported: PlanExport | null; isStarting: boolean; onStart: () => void }) {
  const canExport = plan.status === 'verified' && validation?.status === 'passed' && validation.plan_revision === plan.revision
  return (
    <section className="panel export-panel">
      <div className="panel-heading"><div><p className="eyebrow">Шаг 7</p><h2>Экспорт результата</h2><p className="section-description">Неизменяемый комплект содержит DXF, JSON-план и отчёт в JSON и Markdown.</p></div>{!exported && <button className="button button-primary" type="button" disabled={!canExport || isStarting || job?.status === 'queued' || job?.status === 'running'} onClick={onStart}>{job?.status === 'queued' || job?.status === 'running' ? 'Формируем…' : 'Сформировать экспорт'}</button>}</div>
      {exported ? <div className="artifact-grid">{exported.artifacts.map((artifact) => <a href={artifactDownloadUrl(projectId, artifact.id)} key={artifact.id} download><span>{artifact.format.toUpperCase()}</span><div><strong>{artifact.download_name}</strong><small>{formatBytes(artifact.size_bytes)} · {artifact.kind}</small></div><b>Скачать</b></a>)}</div> : job?.status === 'failed' ? <InlineError error={new Error(job.error ?? 'Экспорт завершился с ошибкой')} /> : <p className="muted">{canExport ? 'План готов к формированию экспортного комплекта.' : 'Экспорт станет доступен после успешной проверки текущей ревизии.'}</p>}
    </section>
  )
}

function JobPanel({ eyebrow, title, job, error, isRetrying = false, onRetry }: { eyebrow: string; title: string; job: Job; error: unknown; isRetrying?: boolean; onRetry?: () => void }) {
  return <section className="panel compact-panel"><div className="panel-heading"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div><span className={`status-pill status-${job.status}`}>{jobStatusLabel(job.status)}</span></div><div className="job-progress"><div className={`progress-track ${job.status === 'failed' ? 'progress-failed' : ''}`}><span className={job.status} /></div><div><strong>Задача #{job.id}</strong><p>{job.error ?? job.stage ?? jobStatusLabel(job.status)}</p></div>{['queued', 'running'].includes(job.status) && <span className="spinner" />}</div>{job.status === 'failed' && onRetry && <div className="retry-row"><button className="button button-primary" type="button" disabled={isRetrying} onClick={onRetry}>{isRetrying ? 'Ставим в очередь…' : 'Запустить повторно'}</button></div>}{error !== null && error !== undefined && <InlineError error={error} />}</section>
}

function InlineError({ error }: { error: unknown }) {
  return <div className="inline-error" role="alert">{error instanceof Error ? error.message : 'Произошла неизвестная ошибка'}</div>
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div><span>{label}</span><strong>{value}</strong></div>
}

function numberFromJob(job: Job | null, key: string): number | null {
  const value = job?.status === 'succeeded' ? job.result?.[key] : null
  return typeof value === 'number' ? value : null
}

function plantingTypeLabel(type: PlantingType) { return type === 'tree' ? 'Дерево' : 'Кустарник' }
function planStatusLabel(status: Plan['status']) { return { verified: 'Проверен', invalid: 'Есть нарушения', needs_verification: 'Требует проверки' }[status] }
function validationStatusLabel(status: PlanValidation['status']) { return { passed: 'Проверка пройдена', failed: 'Есть нарушения', needs_verification: 'Требует проверки' }[status] }
function jobStatusLabel(status: Job['status']) { return { queued: 'В очереди', running: 'Выполняется', succeeded: 'Завершено', failed: 'Ошибка' }[status] }
function formatMeters(value: string) { return `${Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} м` }
function formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ` }

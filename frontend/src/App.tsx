import { FormEvent, useCallback, useEffect, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { AnalysisPanel } from './components/AnalysisPanel'
import { ConfigForm } from './components/ConfigForm'
import { PlanWorkspace } from './components/PlanWorkspace'
import {
  createProject,
  getAnalysis,
  getCurrentAnalysis,
  getCurrentConfig,
  getCurrentPlan,
  getCurrentProjectFile,
  getErrorMessage,
  getJob,
  getProject,
  getProjects,
  saveConfig,
  startAnalysis,
  uploadProjectFile,
} from './api'
import type { ConfigPayload, ConfigSnapshot, Job, Plan, PlanValidation, Project, ProjectFile } from './types'

const stepLabels = ['Проект', 'Исходный DXF', 'Анализ', 'Настройки', 'План', 'Проверка', 'Экспорт']
const ACTIVE_PROJECT_KEY = 'greenplan.activeProjectId'

export function App() {
  const queryClient = useQueryClient()
  const [activeProjectId, setActiveProjectId] = useState<number | null>(readActiveProjectId)
  const [project, setProject] = useState<Project | null>(null)
  const [projectFile, setProjectFile] = useState<ProjectFile | null>(null)
  const [analysisJob, setAnalysisJob] = useState<Job | null>(null)
  const [savedConfig, setSavedConfig] = useState<ConfigSnapshot | null>(null)
  const [resumePlanId, setResumePlanId] = useState<number | null>(null)
  const [planProgress, setPlanProgress] = useState<{ plan: Plan | null; validation: PlanValidation | null; exported: boolean }>({
    plan: null,
    validation: null,
    exported: false,
  })
  const updatePlanProgress = useCallback((progress: { plan: Plan | null; validation: PlanValidation | null; exported: boolean }) => {
    setPlanProgress(progress)
  }, [])

  const projectsQuery = useQuery({
    queryKey: ['projects'],
    queryFn: getProjects,
  })

  const restoreQuery = useQuery({
    queryKey: ['workspace', activeProjectId],
    queryFn: async () => {
      const restoredProject = await getProject(activeProjectId!)
      const [restoredFile, restoredAnalysis, restoredConfig, restoredPlan] = await Promise.all([
        getCurrentProjectFile(activeProjectId!),
        getCurrentAnalysis(activeProjectId!),
        getCurrentConfig(activeProjectId!),
        getCurrentPlan(activeProjectId!),
      ])
      const restoredAnalysisJob = restoredAnalysis ? await getJob(restoredAnalysis.job_id) : null
      return { restoredProject, restoredFile, restoredAnalysisJob, restoredConfig, restoredPlan }
    },
    enabled: activeProjectId !== null,
    retry: false,
    onSuccess: ({ restoredProject, restoredFile, restoredAnalysisJob, restoredConfig, restoredPlan }) => {
      setProject(restoredProject)
      setProjectFile(restoredFile)
      setAnalysisJob(restoredAnalysisJob)
      setSavedConfig(restoredConfig)
      setResumePlanId(restoredPlan?.id ?? null)
    },
    onError: () => {
      setActiveProjectId(null)
      clearWorkspace()
    },
  })

  useEffect(() => {
    if (activeProjectId === null) {
      localStorage.removeItem(ACTIVE_PROJECT_KEY)
    } else {
      localStorage.setItem(ACTIVE_PROJECT_KEY, String(activeProjectId))
    }
  }, [activeProjectId])

  const jobQuery = useQuery<Job>({
    queryKey: ['job', analysisJob?.id],
    queryFn: () => getJob(analysisJob!.id),
    enabled: analysisJob !== null,
    initialData: analysisJob ?? undefined,
    refetchInterval: (job) => (job && (job.status === 'queued' || job.status === 'running') ? 1000 : false),
    onSuccess: (job) => setAnalysisJob(job),
  })

  const analysisIsReady = analysisJob?.status === 'succeeded'
  const analysisQuery = useQuery({
    queryKey: ['analysis', project?.id, analysisJob?.id],
    queryFn: () => getAnalysis(project!.id),
    enabled: project !== null && analysisIsReady,
  })

  const createMutation = useMutation({
    mutationFn: createProject,
    onSuccess: (createdProject) => {
      void queryClient.invalidateQueries({ queryKey: ['projects'] })
      setProject(createdProject)
      setActiveProjectId(createdProject.id)
      setProjectFile(null)
      setAnalysisJob(null)
      setSavedConfig(null)
      setResumePlanId(null)
      setPlanProgress({ plan: null, validation: null, exported: false })
    },
  })

  const uploadMutation = useMutation({
    mutationFn: ({ projectId, file }: { projectId: number; file: File }) => uploadProjectFile(projectId, file),
    onSuccess: (uploadedFile) => {
      setProjectFile(uploadedFile)
      setAnalysisJob(null)
      setSavedConfig(null)
      setResumePlanId(null)
      setPlanProgress({ plan: null, validation: null, exported: false })
    },
  })

  const analysisMutation = useMutation({
    mutationFn: startAnalysis,
    onSuccess: (job) => {
      setAnalysisJob(job)
      setSavedConfig(null)
      setResumePlanId(null)
      setPlanProgress({ plan: null, validation: null, exported: false })
    },
  })

  const configMutation = useMutation({
    mutationFn: ({ projectId, payload }: { projectId: number; payload: ConfigPayload }) =>
      saveConfig(projectId, payload),
    onSuccess: (config) => {
      setSavedConfig(config)
      setResumePlanId(null)
      setPlanProgress({ plan: null, validation: null, exported: false })
    },
  })

  const currentStep = planProgress.exported
    ? 7
    : planProgress.validation
      ? 6
      : planProgress.plan
        ? 5
        : savedConfig
          ? 4
          : analysisQuery.data
            ? 3
            : projectFile
              ? 2
              : project
                ? 1
                : 0
  const error = createMutation.error ?? uploadMutation.error ?? analysisMutation.error ?? jobQuery.error ?? analysisQuery.error
    ?? configMutation.error ?? projectsQuery.error ?? restoreQuery.error

  function clearWorkspace() {
    setProject(null)
    setProjectFile(null)
    setAnalysisJob(null)
    setSavedConfig(null)
    setResumePlanId(null)
    setPlanProgress({ plan: null, validation: null, exported: false })
  }

  function chooseProject(projectId: number) {
    clearWorkspace()
    setActiveProjectId(projectId)
  }

  function closeProject() {
    setActiveProjectId(null)
    clearWorkspace()
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/static/" aria-label="Автосад — главная">
          <img className="brand-mark" src={`${import.meta.env.BASE_URL}brand/avtosad-logo.jpg`} alt="" width="60" height="60" />
          <span><b>Автосад</b><small>Интеллектуальное планирование<br />городского озеленения</small></span>
        </a>
        <div className="topbar-note">
          <span className="live-dot" />
          Локальная рабочая среда
        </div>
      </header>

      <main>
        <section className="hero">
          <div>
            <p className="eyebrow">Проектирование на основе CAD</p>
            <h1>От чертежа к проверенному плану озеленения</h1>
            <p className="hero-copy">
              Загрузите DXF, подтвердите структуру участка и подготовьте воспроизводимые входные данные для расчёта.
            </p>
          </div>
          <div className="hero-figure" aria-hidden="true">
            <div className="plot-outline"><span /><span /><span /><span /><span /></div>
            <div className="hero-caption"><b>2D · локальные метры</b><small>Диагностическое представление</small></div>
          </div>
        </section>

        <nav className="stepper" aria-label="Этапы настройки проекта">
          {stepLabels.map((label, index) => (
            <div className={`step ${index < currentStep ? 'step-done' : ''} ${index === currentStep ? 'step-current' : ''}`} key={label}>
              <span>{index < currentStep ? '✓' : index + 1}</span>
              <div><small>Этап {index + 1}</small><strong>{label}</strong></div>
            </div>
          ))}
        </nav>

        {error !== null && error !== undefined && (
          <div className="global-error" role="alert">
            <strong>Не удалось выполнить действие</strong><span>{getErrorMessage(error)}</span>
          </div>
        )}

        <div className="workspace-grid">
          <div className="workspace-main">
            <ProjectSection
              project={project}
              projects={projectsQuery.data?.items ?? []}
              isRestoring={restoreQuery.isFetching}
              isSubmitting={createMutation.isLoading}
              onChoose={chooseProject}
              onClose={closeProject}
              onSubmit={createMutation.mutate}
            />
            {project && (
              <FileSection
                project={project}
                projectFile={projectFile}
                isUploading={uploadMutation.isLoading}
                onUpload={(file) => uploadMutation.mutate({ projectId: project.id, file })}
              />
            )}
            {project && projectFile && (
              <AnalysisJobSection
                projectId={project.id}
                projectFile={projectFile}
                job={analysisJob}
                isStarting={analysisMutation.isLoading}
                onStart={() => analysisMutation.mutate(project.id)}
              />
            )}
            {analysisQuery.data && <AnalysisPanel analysis={analysisQuery.data} />}
            {analysisQuery.data && project && (
              <ConfigForm
                key={analysisQuery.data.id}
                analysis={analysisQuery.data}
                isSaving={configMutation.isLoading}
                savedConfig={savedConfig}
                onSave={(payload) => configMutation.mutate({ projectId: project.id, payload })}
              />
            )}
            {savedConfig && project && (
              <PlanWorkspace key={`${project.id}-${savedConfig.id}`} projectId={project.id} initialPlanId={resumePlanId} onProgress={updatePlanProgress} />
            )}
          </div>

          <aside className="context-panel">
            <p className="eyebrow">Текущий контекст</p>
            <h2>{project?.name ?? 'Новый проект'}</h2>
            <ContextRow label="Проект" value={project ? `#${project.id}` : 'Не создан'} state={project ? 'ready' : 'pending'} />
            <ContextRow label="Исходник" value={projectFile ? `${projectFile.original_name} · v${projectFile.version}` : 'Не загружен'} state={projectFile ? 'ready' : 'pending'} />
            <ContextRow label="Анализ" value={analysisJob ? jobStatusLabel(analysisJob) : 'Не запускался'} state={analysisJob?.status === 'succeeded' ? 'ready' : analysisJob?.status === 'failed' ? 'error' : 'pending'} />
            <ContextRow label="Конфигурация" value={savedConfig ? `Версия ${savedConfig.version}` : 'Не сохранена'} state={savedConfig ? 'ready' : 'pending'} />
            <ContextRow label="План" value={planProgress.plan ? `#${planProgress.plan.id} · ревизия ${planProgress.plan.revision}` : 'Не создан'} state={planProgress.plan ? 'ready' : 'pending'} />
            <ContextRow label="Проверка" value={planProgress.validation ? validationLabel(planProgress.validation.status) : 'Не выполнена'} state={planProgress.validation?.status === 'passed' ? 'ready' : planProgress.validation?.status === 'failed' ? 'error' : 'pending'} />
            <ContextRow label="Экспорт" value={planProgress.exported ? 'Комплект готов' : 'Не сформирован'} state={planProgress.exported ? 'ready' : 'pending'} />
            <div className="context-note">
              <strong>Сейчас принимается DXF</strong>
              <p>DWG и DWF нужно предварительно преобразовать в DXF без потери структуры слоёв.</p>
            </div>
          </aside>
        </div>
      </main>
      <footer><span>MVP by Дабл тим</span><span>Расчёты выполняются локально</span></footer>
    </div>
  )
}

function ProjectSection({ project, projects, isRestoring, isSubmitting, onChoose, onClose, onSubmit }: {
  project: Project | null
  projects: Project[]
  isRestoring: boolean
  isSubmitting: boolean
  onChoose: (projectId: number) => void
  onClose: () => void
  onSubmit: (data: { name: string; description: string | null }) => void
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [selectedProjectId, setSelectedProjectId] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit({ name, description: description.trim() || null })
  }

  return (
    <section className={`panel compact-panel ${project ? 'panel-complete' : ''}`}>
      <div className="panel-heading">
        <div><p className="eyebrow">Шаг 1</p><h2>Проект</h2></div>
        {project && <span className="status-pill status-success">Проект #{project.id}</span>}
      </div>
      {project ? (
        <div className="completed-summary"><strong>{project.name}</strong><span>{project.description || 'Без описания'}</span><button className="text-button" type="button" onClick={onClose}>Выбрать другой проект</button></div>
      ) : (
        <div className="project-entry">
          {projects.length > 0 && (
            <div className="existing-project-row">
              <label><span>Продолжить существующий проект</span><select value={selectedProjectId} onChange={(event) => setSelectedProjectId(event.target.value)}><option value="">Выберите проект</option>{projects.map((item) => <option value={item.id} key={item.id}>#{item.id} · {item.name}</option>)}</select></label>
              <button className="button button-secondary" type="button" disabled={!selectedProjectId || isRestoring} onClick={() => onChoose(Number(selectedProjectId))}>{isRestoring ? 'Восстанавливаем…' : 'Открыть проект'}</button>
            </div>
          )}
          <form className="inline-form" onSubmit={submit}>
            <label><span>Название нового проекта</span><input value={name} minLength={2} maxLength={255} required placeholder="Сквер на Центральной улице" onChange={(event) => setName(event.target.value)} /></label>
            <label className="wide-field"><span>Описание</span><input value={description} maxLength={2000} placeholder="Необязательно" onChange={(event) => setDescription(event.target.value)} /></label>
            <button className="button button-primary" type="submit" disabled={isSubmitting}>{isSubmitting ? 'Создаём…' : 'Создать проект'}</button>
          </form>
        </div>
      )}
    </section>
  )
}

function readActiveProjectId(): number | null {
  const value = Number(localStorage.getItem(ACTIVE_PROJECT_KEY))
  return Number.isSafeInteger(value) && value > 0 ? value : null
}

function FileSection({ project, projectFile, isUploading, onUpload }: { project: Project; projectFile: ProjectFile | null; isUploading: boolean; onUpload: (file: File) => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [localError, setLocalError] = useState<string | null>(null)

  function submit(event: FormEvent) {
    event.preventDefault()
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.dxf')) {
      setLocalError('Для анализа выберите файл с расширением .dxf')
      return
    }
    setLocalError(null)
    onUpload(file)
  }

  return (
    <section className={`panel compact-panel ${projectFile ? 'panel-complete' : ''}`}>
      <div className="panel-heading">
        <div><p className="eyebrow">Шаг 2</p><h2>Загрузите исходный DXF</h2></div>
        {projectFile && <span className="status-pill status-success">Файл готов</span>}
      </div>
      {projectFile ? (
        <div className="file-summary"><span className="file-icon">DXF</span><div><strong>{projectFile.original_name}</strong><small>{formatBytes(projectFile.size_bytes)} · SHA-256 {projectFile.sha256.slice(0, 12)}…</small></div></div>
      ) : (
        <form className="upload-form" onSubmit={submit}>
          <label className="drop-zone">
            <input type="file" accept=".dxf,application/dxf" onChange={(event) => setFile(event.target.files?.[0] ?? null)} />
            <span className="upload-symbol">↥</span>
            <strong>{file?.name ?? 'Выберите DXF-файл'}</strong>
            <small>{file ? formatBytes(file.size) : 'До 200 МБ · исходник сохраняется без изменений'}</small>
          </label>
          {localError && <p className="field-error">{localError}</p>}
          <button className="button button-primary" type="submit" disabled={!file || isUploading}>{isUploading ? 'Загружаем…' : `Загрузить в проект #${project.id}`}</button>
        </form>
      )}
    </section>
  )
}

function AnalysisJobSection({ projectId, projectFile, job, isStarting, onStart }: { projectId: number; projectFile: ProjectFile; job: Job | null; isStarting: boolean; onStart: () => void }) {
  return (
    <section className="panel compact-panel">
      <div className="panel-heading">
        <div><p className="eyebrow">Шаг 3</p><h2>Проанализируйте структуру</h2></div>
        {job && <span className={`status-pill status-${job.status}`}>{jobStatusLabel(job)}</span>}
      </div>
      {!job ? (
        <div className="action-row">
          <p className="section-description">Анализатор прочитает слои, блоки, единицы, внешние ссылки и неподдерживаемые сущности файла версии {projectFile.version}.</p>
          <button className="button button-primary" type="button" onClick={onStart} disabled={isStarting || projectFile.status !== 'ready'}>{isStarting ? 'Ставим в очередь…' : 'Запустить анализ'}</button>
        </div>
      ) : (
        <div>
          <div className="job-progress">
            <div className={`progress-track ${job.status === 'failed' ? 'progress-failed' : ''}`}><span className={job.status} /></div>
            <div><strong>Задача #{job.id}</strong><p>{job.error ?? stageLabel(job.stage, job.status)}</p></div>
            {(job.status === 'queued' || job.status === 'running') && <span className="spinner" aria-label="Задача выполняется" />}
          </div>
          {(job.status === 'succeeded' || job.status === 'failed') && <div className="retry-row"><button className="button button-secondary" type="button" onClick={onStart} disabled={isStarting}>{isStarting ? 'Ставим в очередь…' : 'Повторить анализ'}</button></div>}
        </div>
      )}
      <span className="sr-only">Проект {projectId}</span>
    </section>
  )
}

function ContextRow({ label, value, state }: { label: string; value: string; state: 'ready' | 'pending' | 'error' }) {
  return <div className="context-row"><span className={`context-state ${state}`} /><div><small>{label}</small><strong>{value}</strong></div></div>
}

function jobStatusLabel(job: Job) {
  return statusLabel(job.status)
}

function stageLabel(stage: string | null, status: Job['status']) {
  const labels: Record<string, string> = { starting: 'Подготовка задачи', analyzing_dxf: 'Чтение и анализ DXF', completed: 'Анализ успешно завершён', failed: 'Задача завершилась с ошибкой', interrupted: 'Задача была прервана' }
  return stage ? (labels[stage] ?? stage) : statusLabel(status)
}

function statusLabel(status: Job['status']) {
  return { queued: 'В очереди', running: 'Выполняется', succeeded: 'Завершён', failed: 'Ошибка' }[status]
}

function validationLabel(status: PlanValidation['status']) {
  return { passed: 'Пройдена', failed: 'Есть нарушения', needs_verification: 'Требует проверки' }[status]
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} КБ`
  return `${(bytes / 1024 / 1024).toFixed(1)} МБ`
}

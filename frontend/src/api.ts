import type {
  AgentMessage,
  Analysis,
  ConfigPayload,
  ConfigSnapshot,
  Job,
  Plan,
  PlanExport,
  PlanPreview,
  PlanValidation,
  Planting,
  PlantingType,
  Project,
  ProjectFile,
  ProjectPage,
} from './types'

const API_BASE_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? '/api'

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, init)
  if (!response.ok) {
    let message = `Сервер вернул ошибку ${response.status}`
    try {
      const payload = (await response.json()) as { detail?: unknown; message?: unknown }
      if (typeof payload.detail === 'string') {
        message = payload.detail
      } else if (typeof payload.message === 'string') {
        message = payload.message
      } else if (Array.isArray(payload.detail)) {
        message = payload.detail
          .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)))
          .join('; ')
      }
    } catch {
      // Ответ без JSON сохраняет понятное сообщение со статусом HTTP.
    }
    throw new ApiError(message, response.status)
  }
  return (await response.json()) as T
}

export function createProject(data: { name: string; description: string | null }): Promise<Project> {
  return request<Project>('/projects/', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  })
}

export function getProjects(): Promise<ProjectPage> {
  return request<ProjectPage>('/projects/?page=1&limit=100')
}

export function getProject(projectId: number): Promise<Project> {
  return request<Project>(`/projects/${projectId}`)
}

export function getCurrentProjectFile(projectId: number): Promise<ProjectFile | null> {
  return requestOptional<ProjectFile>(`/projects/${projectId}/files/current`)
}

export function uploadProjectFile(projectId: number, file: File): Promise<ProjectFile> {
  const body = new FormData()
  body.append('file', file)
  return request<ProjectFile>(`/projects/${projectId}/files/`, { method: 'POST', body })
}

export function startAnalysis(projectId: number): Promise<Job> {
  return request<Job>(`/projects/${projectId}/analyze`, { method: 'POST' })
}

export function sendAgentMessage(projectId: number, message: string): Promise<AgentMessage> {
  return request<AgentMessage>(`/projects/${projectId}/agent/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
  })
}

export function getJob(jobId: number): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`)
}

export function getAnalysis(projectId: number): Promise<Analysis> {
  return request<Analysis>(`/projects/${projectId}/analysis`)
}

export function getCurrentAnalysis(projectId: number): Promise<Analysis | null> {
  return requestOptional<Analysis>(`/projects/${projectId}/analysis`)
}

export function saveConfig(projectId: number, payload: ConfigPayload): Promise<ConfigSnapshot> {
  return request<ConfigSnapshot>(`/projects/${projectId}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getCurrentConfig(projectId: number): Promise<ConfigSnapshot | null> {
  return requestOptional<ConfigSnapshot>(`/projects/${projectId}/config`)
}

export function startPlanGeneration(projectId: number): Promise<Job> {
  return request<Job>(`/projects/${projectId}/plans`, { method: 'POST' })
}

export function getPlan(projectId: number, planId: number): Promise<Plan> {
  return request<Plan>(`/projects/${projectId}/plans/${planId}`)
}

export function getCurrentPlan(projectId: number): Promise<Plan | null> {
  return requestOptional<Plan>(`/projects/${projectId}/plans/current`)
}

export function getPlanPreview(projectId: number, planId: number): Promise<PlanPreview> {
  return request<PlanPreview>(`/projects/${projectId}/plans/${planId}/preview`)
}

export function addPlanting(
  projectId: number,
  planId: number,
  revision: number,
  payload: { type: PlantingType; x_m: number; y_m: number; species: string | null },
): Promise<{ plan_revision: number; planting: Planting }> {
  return request(`/projects/${projectId}/plans/${planId}/plantings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'If-Match': `"${revision}"` },
    body: JSON.stringify(payload),
  })
}

export function updatePlanting(
  projectId: number,
  planId: number,
  plantingId: string,
  revision: number,
  payload: { type?: PlantingType; x_m?: number; y_m?: number; species?: string | null },
): Promise<{ plan_revision: number; planting: Planting }> {
  return request(`/projects/${projectId}/plans/${planId}/plantings/${plantingId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', 'If-Match': `"${revision}"` },
    body: JSON.stringify(payload),
  })
}

export async function deletePlanting(
  projectId: number,
  planId: number,
  plantingId: string,
  revision: number,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/projects/${projectId}/plans/${planId}/plantings/${plantingId}`, {
    method: 'DELETE',
    headers: { 'If-Match': `"${revision}"` },
  })
  if (!response.ok) {
    throw new ApiError(`Не удалось удалить посадку: сервер вернул ошибку ${response.status}`, response.status)
  }
}

export function getPlanReport(projectId: number, planId: number): Promise<PlanValidation> {
  return request<PlanValidation>(`/projects/${projectId}/plans/${planId}/report`)
}

export function startPlanValidation(projectId: number, planId: number, revision: number): Promise<Job> {
  return request<Job>(`/projects/${projectId}/plans/${planId}/validate`, {
    method: 'POST',
    headers: { 'If-Match': `"${revision}"` },
  })
}

export function startExport(projectId: number, planId: number, revision: number, draft = false): Promise<Job> {
  return request<Job>(`/projects/${projectId}/plans/${planId}/exports?draft=${draft}`, {
    method: 'POST',
    headers: { 'If-Match': `"${revision}"` },
  })
}

export function getExport(projectId: number, planId: number, exportId: number): Promise<PlanExport> {
  return request<PlanExport>(`/projects/${projectId}/plans/${planId}/exports/${exportId}`)
}

export function artifactDownloadUrl(projectId: number, artifactId: number): string {
  return `${API_BASE_URL}/projects/${projectId}/artifacts/${artifactId}`
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Произошла неизвестная ошибка'
}

async function requestOptional<T>(path: string): Promise<T | null> {
  try {
    return await request<T>(path)
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null
    throw error
  }
}

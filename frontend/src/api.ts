import type { Analysis, ConfigPayload, ConfigSnapshot, Job, Project, ProjectFile } from './types'

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
      const payload = (await response.json()) as { detail?: unknown }
      if (typeof payload.detail === 'string') {
        message = payload.detail
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

export function uploadProjectFile(projectId: number, file: File): Promise<ProjectFile> {
  const body = new FormData()
  body.append('file', file)
  return request<ProjectFile>(`/projects/${projectId}/files/`, { method: 'POST', body })
}

export function startAnalysis(projectId: number): Promise<Job> {
  return request<Job>(`/projects/${projectId}/analyze`, { method: 'POST' })
}

export function getJob(jobId: number): Promise<Job> {
  return request<Job>(`/jobs/${jobId}`)
}

export function getAnalysis(projectId: number): Promise<Analysis> {
  return request<Analysis>(`/projects/${projectId}/analysis`)
}

export function saveConfig(projectId: number, payload: ConfigPayload): Promise<ConfigSnapshot> {
  return request<ConfigSnapshot>(`/projects/${projectId}/config`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : 'Произошла неизвестная ошибка'
}

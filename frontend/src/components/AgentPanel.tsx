import { FormEvent, useState } from 'react'
import { useMutation } from '@tanstack/react-query'

import { sendAgentMessage } from '../api'

export function AgentPanel({ projectId }: { projectId: number }) {
  const [message, setMessage] = useState('')
  const mutation = useMutation({
    mutationFn: (content: string) => sendAgentMessage(projectId, content),
  })

  function submit(event: FormEvent) {
    event.preventDefault()
    const content = message.trim()
    if (!content || mutation.isLoading) return
    mutation.mutate(content)
  }

  return (
    <section className="panel agent-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Помощник проекта</p>
          <h2>LangChain-агент</h2>
          <p className="section-description">Агент читает только сводки и вызывает защищённые операции backend.</p>
        </div>
        <span className="status-pill">Tool calling</span>
      </div>
      <form className="agent-form" onSubmit={submit}>
        <textarea
          value={message}
          maxLength={4000}
          placeholder="Например: что блокирует проект и какой следующий шаг?"
          onChange={(event) => setMessage(event.target.value)}
        />
        <button className="button button-primary" disabled={!message.trim() || mutation.isLoading}>
          {mutation.isLoading ? 'Агент думает…' : 'Отправить'}
        </button>
      </form>
      {mutation.data && (
        <div className="agent-answer">
          <strong>Ответ</strong>
          <p>{mutation.data.message}</p>
          <small>
            Модель: {mutation.data.model}
            {mutation.data.tool_calls.length > 0 ? ` · Инструменты: ${mutation.data.tool_calls.join(', ')}` : ''}
          </small>
        </div>
      )}
      {mutation.error !== null && mutation.error !== undefined && (
        <div className="inline-error" role="alert">
          {mutation.error instanceof Error ? mutation.error.message : 'Агент не смог обработать запрос'}
        </div>
      )}
    </section>
  )
}

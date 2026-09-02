import type { Conversation, Message, ProjectItem, SSEEvent } from './types'
import { reduceSSE } from './sse'

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.json() as Promise<T>
}

export async function fetchConversations(): Promise<Conversation[]> {
  return json(await fetch('/api/conversations'))
}

export async function createConversation(title?: string): Promise<Conversation> {
  return json(await fetch('/api/conversations', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(title ? { title } : {}),
  }))
}

export async function fetchConversation(id: number): Promise<{ id: number; messages: Message[] }> {
  return json(await fetch(`/api/conversations/${id}`))
}

export async function fetchProjects(): Promise<ProjectItem[]> {
  return json(await fetch('/api/projects'))
}

export async function abortConversation(id: number): Promise<void> {
  await fetch(`/api/conversations/${id}/abort`, { method: 'POST' })
}

export async function deleteConversation(id: number): Promise<void> {
  await fetch(`/api/conversations/${id}`, { method: 'DELETE' })
}

export async function streamChat(
  id: number, content: string,
  onEvent: (e: SSEEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`/api/conversations/${id}/messages`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  })
  if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`)
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  const buf = { pending: '' }
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    reduceSSE(buf, decoder.decode(value, { stream: true }), onEvent)
  }
  reduceSSE(buf, decoder.decode(), onEvent)
}

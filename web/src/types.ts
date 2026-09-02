export interface Conversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export type MessageKind = 'user' | 'assistant' | 'document'

export interface Message {
  id: number
  conversation_id: number
  role: string
  content: string
  kind: MessageKind
  meta: Record<string, unknown>
  created_at: string
}

export interface ProjectItem {
  filename: string
  size: number
  mtime: number
}

export type SSEEventType = 'text_delta' | 'tool_use' | 'document_saved' | 'done' | 'error'

export interface SSEEvent<T = unknown> {
  event: SSEEventType
  data: T
}

export interface ToolUseData {
  id: string
  name: string
  input: Record<string, unknown>
}

export interface DocSavedData {
  filename: string
  path: string
}

export interface DoneData {
  stop_reason: string | null
  is_error: boolean
  session_id: string | null
}

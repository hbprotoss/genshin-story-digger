import { useCallback, useEffect, useRef, useState } from 'react'
import { abortConversation, fetchConversation, streamChat } from '../api'
import type { Message, SSEEvent, ToolUseData } from '../types'
import MessageView from './Message'
import ToolCallView from './ToolCall'
import DocCardView from './DocCard'

export default function ChatView({ conversationId }: { conversationId: number }) {
  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [toolCalls, setToolCalls] = useState<ToolUseData[]>([])
  const [docs, setDocs] = useState<string[]>([])
  const abortRef = useRef<AbortController | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    let alive = true
    setMessages([])
    setToolCalls([])
    setDocs([])
    fetchConversation(conversationId).then(({ messages }) => {
      if (!alive) return
      setMessages(messages)
    })
    return () => { alive = false }
  }, [conversationId])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, toolCalls, docs])

  const handleEvent = useCallback((e: SSEEvent) => {
    if (e.event === 'text_delta') {
      const text = String((e.data as { text: string }).text)
      setMessages((prev) => {
        const last = prev[prev.length - 1]
        if (last && last.kind === 'assistant') {
          const updated = [...prev]
          updated[updated.length - 1] = { ...last, content: last.content + text }
          return updated
        }
        return [...prev, { id: -1, conversation_id: conversationId, role: 'assistant',
          kind: 'assistant', content: text, meta: {}, created_at: '' }]
      })
    } else if (e.event === 'tool_use') {
      setToolCalls((prev) => [...prev, e.data as ToolUseData])
    } else if (e.event === 'document_saved') {
      setDocs((prev) => [...prev, (e.data as { filename: string }).filename])
    } else if (e.event === 'done' || e.event === 'error') {
      setBusy(false)
    }
  }, [conversationId])

  const send = async () => {
    const content = input.trim()
    if (!content || busy) return
    setMessages((prev) => [...prev, { id: -1, conversation_id: conversationId, role: 'user',
      kind: 'user', content, meta: {}, created_at: '' } as Message])
    setToolCalls([])
    setDocs([])
    setInput('')
    setBusy(true)
    const ac = new AbortController()
    abortRef.current = ac
    try {
      await streamChat(conversationId, content, handleEvent, ac.signal)
    } catch { setBusy(false) }
    setBusy(false)
  }

  const stop = () => {
    abortConversation(conversationId)
    abortRef.current?.abort()
    setBusy(false)
  }

  return (
    <div className="chat">
      <div className="messages">
        {messages.map((m, i) =>
          m.kind === 'document'
            ? null
            : <MessageView key={m.kind === 'assistant' ? `a-${i}` : `u-${i}`} msg={m} />,
        )}
        {toolCalls.length > 0 && (
          <div className="toolcalls">
            {toolCalls.map((c) => <ToolCallView key={c.id} call={c} />)}
          </div>
        )}
        {docs.map((d) => <DocCardView key={d} filename={d} />)}
        <div ref={bottomRef} />
      </div>
      <div className="composer">
        <textarea value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() } }}
          placeholder="输入故事线关键词…" />
        {busy
          ? <button onClick={stop}>停止</button>
          : <button onClick={send} disabled={!input.trim()}>发送</button>}
      </div>
    </div>
  )
}

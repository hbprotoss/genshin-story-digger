import type { SSEEvent } from './types'

/** 把一段 SSE 响应文本解析为事件并回调（容错：被网络切成多块的缓冲）。 */
export function parseSSEBlock(block: string): SSEEvent[] {
  const events: SSEEvent[] = []
  const lines = block.split(/\r?\n/)
  let eventName = 'message'
  const dataLines: string[] = []
  const flush = () => {
    if (dataLines.length) {
      let data: unknown = dataLines.join('\n')
      try { data = JSON.parse(String(data)) } catch { /* 保持原字符串 */ }
      events.push({ event: eventName as SSEEvent['event'], data })
      dataLines.length = 0
    }
  }
  for (const line of lines) {
    if (!line) { flush(); continue }
    const [key, ...rest] = line.split(':')
    const value = rest.join(':').trim()
    if (key === 'event') eventName = value
    else if (key === 'data') dataLines.push(value)
  }
  flush()
  return events
}

/** SSE 增量 reducer：accumulated 负责跨块缓冲未结束的 data 行。 */
export function reduceSSE(accumulated: { pending: string }, chunk: string,
                          onEvent: (e: SSEEvent) => void): void {
  accumulated.pending += chunk
  const idx = accumulated.pending.lastIndexOf('\n\n')
  if (idx === -1) return
  const complete = accumulated.pending.slice(0, idx)
  accumulated.pending = accumulated.pending.slice(idx + 2)
  for (const ev of parseSSEBlock(complete)) onEvent(ev)
}

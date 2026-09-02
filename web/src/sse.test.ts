import { describe, it, expect } from 'vitest'
import { parseSSEBlock, reduceSSE } from './sse'

describe('parseSSEBlock', () => {
  it('parses typed event with json data', () => {
    const es = parseSSEBlock('event: text_delta\ndata: {"text":"你好"}\n\nevent: done\ndata: {"session_id":null}\n\n')
    expect(es).toHaveLength(2)
    expect(es[0].event).toBe('text_delta')
    expect((es[0].data as { text: string }).text).toBe('你好')
  })
  it('falls back to raw string when data not json', () => {
    const es = parseSSEBlock('event: x\ndata: plain text\n\n')
    expect(es[0].data).toBe('plain text')
  })
})

describe('reduceSSE', () => {
  it('buffers partial chunks and flushes on blank line', () => {
    const buf = { pending: '' }
    const seen: string[] = []
    reduceSSE(buf, 'event: text_delta\ndata: {', (e) => seen.push(e.event))
    expect(seen).toHaveLength(0)
    reduceSSE(buf, '"hi"}\n\n', (e) => seen.push(e.event))
    expect(seen).toEqual(['text_delta'])
  })
})

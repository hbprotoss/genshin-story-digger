import { beforeEach, afterEach, describe, it, expect, vi } from 'vitest'
import { fetchConversations, streamChat, abortConversation, deleteConversation } from './api'

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchConversations', () => {
  it('GETs conversations', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify([])))
    const out = await fetchConversations()
    expect(out).toEqual([])
    expect(fetch).toHaveBeenCalledWith('/api/conversations')
  })
})

describe('abortConversation', () => {
  it('POSTs abort', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}'))
    await abortConversation(2)
    expect(fetch).toHaveBeenCalled()
  })
})

describe('deleteConversation', () => {
  it('DELETEs the conversation', async () => {
    vi.mocked(fetch).mockResolvedValue(new Response('{}'))
    await deleteConversation(3)
    expect(fetch).toHaveBeenCalledWith('/api/conversations/3', { method: 'DELETE' })
  })
})

describe('streamChat', () => {
  it('yields text_delta events over a read stream', async () => {
    const body = 'event: text_delta\ndata: {"text":"hi"}\n\nevent: done\ndata: {"session_id":"s"}\n\n'
    const stream = new ReadableStream({
      start(c) { c.enqueue(new TextEncoder().encode(body)); c.close() },
    })
    vi.mocked(fetch).mockResolvedValue(new Response(stream, {
      headers: { 'content-type': 'text/event-stream' },
    }))
    const seen: string[] = []
    await streamChat(1, 'hi', (e) => seen.push(e.event))
    expect(seen).toContain('text_delta')
    expect(seen).toContain('done')
  })
})

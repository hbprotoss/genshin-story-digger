import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { vi } from 'vitest'
import * as api from '../api'
import ChatView from './ChatView'

// jsdom 未实现 scrollIntoView，桩掉以免组件 effect 报错
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {}
}

vi.mock('../api', async (importOriginal) => {
  const mod = await importOriginal<typeof api>()
  return {
    ...mod,
    fetchConversation: vi.fn().mockResolvedValue({ id: 1, messages: [] }),
    streamChat: vi.fn().mockImplementation((_id, _content, _onEvent, signal) =>
      new Promise<void>((resolve) => {
        // 挂起，直到外部 abort
        signal?.addEventListener('abort', () => resolve())
      })),
    abortConversation: vi.fn().mockResolvedValue(undefined),
  }
})

test('unmount aborts in-flight stream', async () => {
  const { unmount } = render(<ChatView conversationId={1} />)

  // 等待文本域出现，输入内容后发送按钮变为可用
  const textarea = await screen.findByPlaceholderText('输入故事线关键词…')
  fireEvent.change(textarea, { target: { value: '写故事' } })
  await waitFor(() => expect(screen.getByText('发送')).toBeEnabled())
  fireEvent.click(screen.getByText('发送'))
  await waitFor(() => expect(screen.getByText('停止')).toBeInTheDocument())

  const streamChatMock = api.streamChat as unknown as ReturnType<typeof vi.fn>
  const signal = streamChatMock.mock.calls[0][3] as AbortSignal

  // 卸载触发 abort
  unmount()
  expect(signal.aborted).toBe(true)
})

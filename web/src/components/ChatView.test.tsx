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

// 渲染后等待历史消息加载完成的公共入口
async function renderLoaded(id = 1) {
  const utils = render(<ChatView conversationId={id} />)
  await screen.findByPlaceholderText('输入故事线关键词…')
  return utils
}

test('unmount aborts in-flight stream', async () => {
  const { unmount } = await renderLoaded()

  // 等待文本域出现，输入内容后发送按钮变为可用
  const textarea = screen.getByPlaceholderText('输入故事线关键词…')
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

test('loads historical document cards from conversation messages', async () => {
  // 历史消息中包含 document，刷新后应恢复文档卡片（spec §4.1）
  const fetchMock = api.fetchConversation as unknown as ReturnType<typeof vi.fn>
  fetchMock.mockResolvedValueOnce({
    id: 2,
    messages: [
      { id: 1, conversation_id: 2, role: 'user', kind: 'user', content: '写故事', meta: {}, created_at: '' },
      { id: 2, conversation_id: 2, role: 'assistant', kind: 'document', content: '',
        meta: { filename: '故事线草稿.md' }, created_at: '' },
      { id: 3, conversation_id: 2, role: 'assistant', kind: 'document', content: '',
        meta: { filename: '' }, created_at: '' },
    ],
  })

  await renderLoaded(2)

  // 有 filename 的 document 卡片恢复，空 filename 的被忽略
  await waitFor(() => expect(screen.getByText(/已生成文档：故事线草稿\.md/)).toBeInTheDocument())
  expect(screen.queryByText(/已生成文档：$|已生成文档：查看/)).not.toBeInTheDocument()
})

import { render, screen } from '@testing-library/react'
import Message from './Message'

test('renders user bubble', () => {
  render(<Message msg={{ id: 1, conversation_id: 1, role: 'user', content: 'hello', kind: 'user', meta: {}, created_at: '' }} />)
  expect(screen.getByText('hello')).toBeInTheDocument()
})

test('renders assistant markdown', () => {
  render(<Message msg={{ id: 2, conversation_id: 1, role: 'assistant', content: '**bold**', kind: 'assistant', meta: {}, created_at: '' }} />)
  expect(screen.getByText('bold').tagName).toBe('STRONG')
})

test('renders document card', () => {
  render(<Message msg={{ id: 3, conversation_id: 1, role: 'assistant', content: '', kind: 'document', meta: { filename: 'a.md' }, created_at: '' }} />)
  expect(screen.getByText(/已生成文档/)).toBeInTheDocument()
})

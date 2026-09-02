import { render, screen } from '@testing-library/react'
import ToolCall from './ToolCall'

test('shows label and keyword detail for search_texts', () => {
  render(<ToolCall call={{ id: 't1', name: 'mcp__mongo__search_texts', input: { keywords: ['渊下'] } }} />)
  expect(screen.getByText(/检索原文/)).toBeInTheDocument()
  expect(screen.getByText(/关键词：渊下/)).toBeInTheDocument()
})

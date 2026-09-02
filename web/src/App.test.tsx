import { render, screen } from '@testing-library/react'
import { vi } from 'vitest'
import App from './App'

test('renders new conversation button', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify([]))))
  render(<App />)
  expect(await screen.findByText(/新对话/)).toBeInTheDocument()
  vi.unstubAllGlobals()
})

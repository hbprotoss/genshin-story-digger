import { render, screen } from '@testing-library/react'
import App from './App'

test('renders brand', () => {
  render(<App />)
  expect(screen.getByText(/story digger/i)).toBeInTheDocument()
})

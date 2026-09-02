import { render, screen } from '@testing-library/react'
import DocCard from './DocCard'

test('renders filename and links', () => {
  render(<DocCard filename="渊下宫.md" />)
  expect(screen.getByText(/已生成文档：渊下宫\.md/)).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '查看' }).getAttribute('href')).toContain(encodeURIComponent('渊下宫.md'))
})

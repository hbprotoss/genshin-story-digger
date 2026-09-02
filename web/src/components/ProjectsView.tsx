import { useEffect, useState } from 'react'
import { fetchProjects } from '../api'
import type { ProjectItem } from '../types'

export default function ProjectsView() {
  const [items, setItems] = useState<ProjectItem[]>([])
  useEffect(() => {
    fetchProjects().then(setItems).catch(() => {})
  }, [])
  return (
    <div className="projects">
      <h2>已生成文档</h2>
      <ul>
        {items.map((p) => (
          <li key={p.filename}>
            <a href={`/api/projects/${encodeURIComponent(p.filename)}`} target="_blank" rel="noreferrer">
              {p.filename}
            </a>
          </li>
        ))}
      </ul>
    </div>
  )
}

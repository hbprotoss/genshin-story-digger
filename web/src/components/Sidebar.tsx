import type { Conversation } from '../types'

export default function Sidebar({ items, activeId, onSelect, onNew, onDelete }:
  { items: Conversation[]; activeId: number | null; onSelect: (id: number) => void;
    onNew: () => void; onDelete: (id: number) => void }) {
  return (
    <aside className="sidebar">
      <button className="new" onClick={onNew}>＋ 新对话</button>
      <ul>
        {items.map((c) => (
          <li key={c.id} className={c.id === activeId ? 'active' : ''} onClick={() => onSelect(c.id)}>
            <span className="title">{c.title || `对话 ${c.id}`}</span>
            <button className="del" onClick={(e) => { e.stopPropagation(); onDelete(c.id) }}>✕</button>
          </li>
        ))}
      </ul>
    </aside>
  )
}

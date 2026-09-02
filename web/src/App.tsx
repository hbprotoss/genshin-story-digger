import { useCallback, useEffect, useState } from 'react'
import { createConversation, deleteConversation, fetchConversations } from './api'
import type { Conversation } from './types'
import Sidebar from './components/Sidebar'
import ChatView from './components/ChatView'
import ProjectsView from './components/ProjectsView'

type View = { kind: 'chat'; id: number } | { kind: 'projects' }

export default function App() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [view, setView] = useState<View | null>(null)

  const load = useCallback(() => {
    fetchConversations().then((cs) => {
      setConversations(cs)
      if (!view && cs.length > 0) setView({ kind: 'chat', id: cs[0].id })
    }).catch(() => {})
  }, [view])

  useEffect(load, [load])

  const onNew = async () => {
    const c = await createConversation()
    setConversations((prev) => [c, ...prev])
    setView({ kind: 'chat', id: c.id })
  }

  const onDelete = async (id: number) => {
    await deleteConversation(id)
    const rest = conversations.filter((c) => c.id !== id)
    setConversations(rest)
    setView(rest.length ? { kind: 'chat', id: rest[0].id } : null)
  }

  return (
    <div className="layout">
      <Sidebar
        items={conversations}
        activeId={view?.kind === 'chat' ? view.id : null}
        onSelect={(id) => setView({ kind: 'chat', id })}
        onNew={onNew}
        onDelete={onDelete}
      />
      <main className="main">
        <div className="tabs">
          <button onClick={() => setView({ kind: 'projects' })}>项目</button>
        </div>
        {view?.kind === 'projects' && <ProjectsView />}
        {view?.kind === 'chat' && <ChatView key={view.id} conversationId={view.id} />}
        {!view && <div className="empty">选择或新建一个对话开始</div>}
      </main>
    </div>
  )
}

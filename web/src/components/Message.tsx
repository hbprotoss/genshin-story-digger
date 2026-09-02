import ReactMarkdown from 'react-markdown'
import type { Message as MessageT } from '../types'
import DocCard from './DocCard'

export default function Message({ msg }: { msg: MessageT }) {
  if (msg.kind === 'document') {
    return <div className="msg document"><DocCard filename={String(msg.meta.filename ?? '')} /></div>
  }
  if (msg.role === 'user') {
    return <div className="msg user"><div className="bubble">{msg.content}</div></div>
  }
  return (
    <div className="msg assistant">
      <div className="bubble markdown">
        <ReactMarkdown>{msg.content}</ReactMarkdown>
      </div>
    </div>
  )
}

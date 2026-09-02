import type { ToolUseData } from '../types'

const TOOL_LABEL: Record<string, string> = {
  'mcp__mongo__search_texts': '🔍 检索原文',
  'mcp__mongo__get_text': '📖 读取正文',
  'mcp__mongo__get_meta': '🏷️ 查询元数据',
  'mcp__mongo__stats': '📊 查看统计',
  Task: '👥 派发章节',
  Write: '📄 写入文档',
}

function fmtInput(name: string, input: Record<string, unknown>): string {
  if (name === 'mcp__mongo__search_texts') {
    const kw = (input.keywords as string[] | undefined) ?? []
    return `关键词：${kw.join('、')}`
  }
  if (name === 'Task') {
    return (input.prompt as string | undefined)?.slice(0, 40) ?? ''
  }
  if (name === 'Write') {
    return String(input.file_path ?? '')
  }
  return ''
}

export default function ToolCall({ call }: { call: ToolUseData }) {
  const label = TOOL_LABEL[call.name] ?? call.name
  const detail = fmtInput(call.name, call.input)
  return (
    <details className="tool-call">
      <summary>{label}{detail ? ` · ${detail}` : ''}</summary>
      <pre>{JSON.stringify(call.input, null, 2)}</pre>
    </details>
  )
}

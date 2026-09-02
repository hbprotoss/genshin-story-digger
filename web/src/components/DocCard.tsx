export default function DocCard({ filename }: { filename: string }) {
  return (
    <div className="doc-card">
      📄 已生成文档：{filename}
      <a href={`/api/projects/${encodeURIComponent(filename)}`} target="_blank" rel="noreferrer">查看</a>
      <a href={`/api/projects/${encodeURIComponent(filename)}?download=1`}>下载</a>
    </div>
  )
}

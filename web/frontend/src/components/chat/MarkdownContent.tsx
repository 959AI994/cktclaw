import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

interface MarkdownContentProps {
  content: string
  className?: string
}

/** Render assistant markdown (GFM: tables, headings, lists). */
export function MarkdownContent({ content, className = '' }: MarkdownContentProps) {
  if (!content) return null
  return (
    <div className={`chat-markdown ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  )
}

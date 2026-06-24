import { useEffect, useRef } from 'react'
import type { ActiveOrchestratorRun, ChatAttachmentRef, ChatMessage, OrchestratorProposal } from '../../types/api'
import { isImageMime, uploadUrl } from '../../lib/uploads'
import { MarkdownContent } from './MarkdownContent'
import { ToolCallCard } from './ToolCallCard'
import { OrchestratorProposalCard } from './OrchestratorProposalCard'
import { OrchestratorRunCard } from './OrchestratorRunCard'

interface ChatThreadProps {
  messages: ChatMessage[]
  streamBuffer: string
  streaming: boolean
  pendingToolCalls: Record<string, { name: string; arguments?: unknown; result?: string | null }>
  orchestratorProposal?: OrchestratorProposal | null
  activeOrchestratorRun?: ActiveOrchestratorRun | null
  onOrchestratorConfirm?: (task: string) => void
  onOrchestratorCancel?: () => void
}

export function ChatThread({
  messages,
  streamBuffer,
  streaming,
  pendingToolCalls,
  orchestratorProposal,
  activeOrchestratorRun,
  onOrchestratorConfirm,
  onOrchestratorCancel,
}: ChatThreadProps) {
  const threadRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = threadRef.current
    if (el) el.scrollTop = el.scrollHeight
  }, [messages, streamBuffer, streaming, pendingToolCalls, activeOrchestratorRun])

  const showEmpty =
    messages.length === 0 && !streaming && !orchestratorProposal && !activeOrchestratorRun

  return (
    <div ref={threadRef} className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
      {showEmpty && (
        <div className="flex flex-col items-center justify-center h-full text-[var(--color-text-dim)]">
          <div className="text-3xl mb-2">✦</div>
          Start a conversation with your AI agent
          <p className="text-xs mt-2">Drag & drop files or images here</p>
        </div>
      )}

      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} />
      ))}

      {orchestratorProposal && onOrchestratorConfirm && onOrchestratorCancel && (
        <OrchestratorProposalCard
          proposal={orchestratorProposal}
          onConfirm={onOrchestratorConfirm}
          onCancel={onOrchestratorCancel}
        />
      )}

      {activeOrchestratorRun && !orchestratorProposal && (
        <OrchestratorRunCard run={activeOrchestratorRun} />
      )}

      {streaming && (
        <div className="flex gap-3">
          <Avatar role="assistant" />
          <div className="flex-1 min-w-0">
            <div className="chat-bubble inline-block max-w-[85%] px-3.5 py-2.5 rounded-xl bg-[var(--color-bg-overlay)] text-sm leading-relaxed streaming-cursor">
              <MarkdownContent content={streamBuffer} />
            </div>
            {Object.values(pendingToolCalls).map((tc, i) => (
              <ToolCallCard key={i} tc={tc} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  const isUser = msg.role === 'user'
  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      <Avatar role={msg.role} />
      <div className={`flex-1 min-w-0 ${isUser ? 'flex flex-col items-end' : ''}`}>
        <div
          className={`chat-bubble inline-block max-w-[85%] px-3.5 py-2.5 rounded-xl text-sm leading-relaxed ${
            isUser
              ? 'bg-[var(--color-accent)] text-white'
              : 'bg-[var(--color-bg-overlay)] text-[var(--color-text)]'
          }`}
        >
          {isUser ? (
            <>
              {msg.content && msg.content !== '(attachments)' && (
                <p className="whitespace-pre-wrap m-0">{msg.content}</p>
              )}
              {msg.attachments?.length ? <MessageAttachments attachments={msg.attachments} inUserBubble /> : null}
            </>
          ) : (
            <MarkdownContent content={msg.content} />
          )}
        </div>
        {(msg.tool_calls || []).map((tc, i) => (
          <ToolCallCard key={i} tc={tc} />
        ))}
      </div>
    </div>
  )
}

function MessageAttachments({
  attachments,
  inUserBubble,
}: {
  attachments: ChatAttachmentRef[]
  inUserBubble?: boolean
}) {
  return (
    <div className={`flex flex-wrap gap-2 ${inUserBubble ? 'mt-2' : 'mt-1'}`}>
      {attachments.map((a) => {
        const url = uploadUrl(a)
        const isImage = isImageMime(a.mime)
        return (
          <div key={a.id} className={`message-attachment ${inUserBubble ? 'message-attachment--user' : ''}`}>
            {isImage ? (
              <a href={url} target="_blank" rel="noreferrer">
                <img src={url} alt={a.filename} className="message-attachment-img" />
              </a>
            ) : (
              <a href={url} target="_blank" rel="noreferrer" className="message-attachment-file">
                📄 {a.filename}
              </a>
            )}
          </div>
        )
      })}
    </div>
  )
}

function Avatar({ role }: { role: string }) {
  const isUser = role === 'user'
  return (
    <div
      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
        isUser ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-purple)] text-white'
      }`}
    >
      {isUser ? 'U' : 'AI'}
    </div>
  )
}

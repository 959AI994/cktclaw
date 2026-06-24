import { useRef } from 'react'
import type { UploadMeta } from '../../types/api'
import { AttachmentUploader } from '../upload/AttachmentUploader'
import { Button } from '../ui/Button'

interface ChatInputProps {
  value: string
  streaming: boolean
  useTools: boolean
  sessionId: string
  pendingAttachments: UploadMeta[]
  onAttachmentsChange: (attachments: UploadMeta[]) => void
  onChange: (v: string) => void
  onUseToolsChange: (v: boolean) => void
  onSend: () => void
  onAbort: () => void
}

export function ChatInputBar({
  value,
  streaming,
  useTools,
  sessionId,
  pendingAttachments,
  onAttachmentsChange,
  onChange,
  onUseToolsChange,
  onSend,
  onAbort,
}: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const canSend = !streaming && sessionId && (value.trim().length > 0 || pendingAttachments.length > 0)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (canSend) onSend()
    }
  }

  return (
    <div className="border-t border-[var(--color-border)] p-3 bg-[var(--color-bg-surface)]">
      <AttachmentUploader
        sessionId={sessionId}
        attachments={pendingAttachments}
        onChange={onAttachmentsChange}
        disabled={streaming || !sessionId}
        compact
      />
      <textarea
        ref={inputRef}
        rows={2}
        className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] resize-none mt-2"
        placeholder="Type a message… (Enter to send, Shift+Enter for newline)"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        disabled={streaming}
      />
      <div className="flex items-center justify-between mt-2">
        <label className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] cursor-pointer">
          <input type="checkbox" checked={useTools} onChange={(e) => onUseToolsChange(e.target.checked)} />
          Tools
        </label>
        <div className="flex gap-2">
          {streaming && (
            <Button variant="danger" size="sm" onClick={onAbort}>
              Stop
            </Button>
          )}
          <Button variant="primary" onClick={onSend} disabled={!canSend}>
            Send
          </Button>
        </div>
      </div>
    </div>
  )
}

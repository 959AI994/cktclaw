import { useRef } from 'react'
import type { UploadMeta } from '../../types/api'
import { AttachmentUploader } from '../upload/AttachmentUploader'
import { Button } from '../ui/Button'

interface ChatInputProps {
  value: string
  streaming: boolean
  skipOrchestratorConfirm: boolean
  disableTools: boolean
  sessionId: string
  pendingAttachments: UploadMeta[]
  onAttachmentsChange: (attachments: UploadMeta[]) => void
  onChange: (v: string) => void
  onSkipOrchestratorConfirmChange: (v: boolean) => void
  onDisableToolsChange: (v: boolean) => void
  onSend: () => void
  onAbort: () => void
}

export function ChatInputBar({
  value,
  streaming,
  skipOrchestratorConfirm,
  disableTools,
  sessionId,
  pendingAttachments,
  onAttachmentsChange,
  onChange,
  onSkipOrchestratorConfirmChange,
  onDisableToolsChange,
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
      <div className="flex items-center justify-between mt-2 gap-2 flex-wrap">
        <div className="flex items-center gap-3 flex-wrap">
          <label className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] cursor-pointer">
            <input
              type="checkbox"
              checked={skipOrchestratorConfirm}
              onChange={(e) => onSkipOrchestratorConfirmChange(e.target.checked)}
            />
            Orchestrator 免确认
          </label>
          <label className="flex items-center gap-1.5 text-xs text-[var(--color-text-dim)] cursor-pointer" title="Advanced">
            <input
              type="checkbox"
              checked={disableTools}
              onChange={(e) => onDisableToolsChange(e.target.checked)}
            />
            Disable tools
          </label>
        </div>
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

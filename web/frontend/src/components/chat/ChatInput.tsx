import { useRef } from 'react'
import { Button } from '../ui/Button'

interface ChatInputProps {
  value: string
  streaming: boolean
  useTools: boolean
  onChange: (v: string) => void
  onUseToolsChange: (v: boolean) => void
  onSend: () => void
  onAbort: () => void
}

export function ChatInputBar({
  value,
  streaming,
  useTools,
  onChange,
  onUseToolsChange,
  onSend,
  onAbort,
}: ChatInputProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (!streaming && value.trim()) onSend()
    }
  }

  return (
    <div className="border-t border-[var(--color-border)] p-3 bg-[var(--color-bg-surface)]">
      <textarea
        ref={inputRef}
        rows={2}
        className="w-full px-3 py-2 text-sm rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)] outline-none focus:border-[var(--color-accent)] resize-none"
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
          <Button variant="primary" onClick={onSend} disabled={streaming || !value.trim()}>
            Send
          </Button>
        </div>
      </div>
    </div>
  )
}

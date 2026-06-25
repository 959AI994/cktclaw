import { useState } from 'react'
import type { ToolCallInfo } from '../../types/api'
import { safeStringify } from '../../lib/utils'

export function ToolCallCard({ tc }: { tc: ToolCallInfo }) {
  const [open, setOpen] = useState(false)

  return (
    <div className="mt-2 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-xs overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-3 py-1.5 hover:bg-[var(--color-bg-overlay)] cursor-pointer border-none bg-transparent text-[var(--color-text)] text-left"
        onClick={() => setOpen(!open)}
      >
        <span>🔧 {tc.name}</span>
        <span>{open ? '▴' : '▾'}</span>
      </button>
      {open && (
        <div className="px-3 py-2 border-t border-[var(--color-border-muted)]">
          <div className="text-[var(--color-text-secondary)] mb-1">
            Args: <span className="font-[family-name:var(--font-mono)]">{safeStringify(tc.arguments)}</span>
          </div>
          {tc.result ? (
            <div>
              <span className="text-[var(--color-text-secondary)]">Result:</span>{' '}
              <span className="font-[family-name:var(--font-mono)]">{tc.result}</span>
            </div>
          ) : (
            <div className="text-[var(--color-text-dim)]">running…</div>
          )}
        </div>
      )}
    </div>
  )
}

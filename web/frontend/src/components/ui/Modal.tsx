import type { ReactNode } from 'react'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: ReactNode
  children: ReactNode
  actions?: ReactNode
}

export function Modal({ open, onClose, title, children, actions }: ModalProps) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/55 backdrop-blur-sm"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div className="w-full max-w-lg mx-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-elevated)] shadow-2xl p-6">
        <h2 className="text-lg font-semibold mb-4 font-[family-name:var(--font-mono)]">{title}</h2>
        <div className="space-y-3">{children}</div>
        {actions && <div className="flex justify-end gap-2 mt-5">{actions}</div>}
      </div>
    </div>
  )
}

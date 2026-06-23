import type { ReactNode } from 'react'

interface CardProps {
  children: ReactNode
  className?: string
  header?: ReactNode
}

export function Card({ children, className = '', header }: CardProps) {
  return (
    <div
      className={`rounded-[10px] border border-[var(--color-border)] bg-[var(--color-bg-surface)] shadow-sm ${className}`}
    >
      {header && (
        <div className="px-4 py-2.5 border-b border-[var(--color-border-muted)] text-sm font-semibold text-[var(--color-text-secondary)]">
          {header}
        </div>
      )}
      <div className={header ? 'p-4' : ''}>{children}</div>
    </div>
  )
}

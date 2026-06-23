import type { ReactNode } from 'react'

const variants: Record<string, string> = {
  accent: 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)]',
  success: 'bg-green-500/15 text-[var(--color-success)]',
  warning: 'bg-yellow-500/15 text-[var(--color-warning)]',
  danger: 'bg-red-500/15 text-[var(--color-danger)]',
  muted: 'bg-[var(--color-bg-overlay)] text-[var(--color-text-dim)]',
  purple: 'bg-purple-500/15 text-[var(--color-purple)]',
  cyan: 'bg-cyan-500/15 text-[var(--color-cyan)]',
}

interface BadgeProps {
  children: ReactNode
  variant?: keyof typeof variants
  className?: string
}

export function Badge({ children, variant = 'muted', className = '' }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center px-1.5 py-0.5 rounded text-[0.72rem] font-medium ${variants[variant]} ${className}`}
    >
      {children}
    </span>
  )
}

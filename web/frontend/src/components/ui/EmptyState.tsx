import { Button } from './Button'

type EmptyStateVariant = 'empty' | 'loading' | 'error'

interface EmptyStateProps {
  variant?: EmptyStateVariant
  title: string
  description?: string
  onRefresh?: () => void
}

export function EmptyState({ variant = 'empty', title, description, onRefresh }: EmptyStateProps) {
  const icon = variant === 'loading' ? '…' : variant === 'error' ? '!' : '○'

  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-bg-surface)]/50">
      <div
        className={`text-2xl mb-3 ${variant === 'loading' ? 'animate-pulse text-[var(--color-accent)]' : 'text-[var(--color-text-dim)]'}`}
      >
        {icon}
      </div>
      <h3 className="text-sm font-medium mb-1">{title}</h3>
      {description && <p className="text-xs text-[var(--color-text-secondary)] max-w-md mb-4">{description}</p>}
      {onRefresh && variant !== 'loading' && (
        <Button size="sm" onClick={onRefresh}>
          ↻ Refresh
        </Button>
      )}
    </div>
  )
}

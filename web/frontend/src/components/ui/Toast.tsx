import { useAppStore } from '../../store/appStore'

const levelStyles = {
  success: 'border-l-[var(--color-success)]',
  error: 'border-l-[var(--color-danger)]',
  info: 'border-l-[var(--color-accent)]',
}

export function ToastContainer() {
  const toasts = useAppStore((s) => s.toasts)
  return (
    <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto px-4 py-2.5 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-elevated)] text-sm shadow-lg border-l-4 ${levelStyles[t.level]}`}
        >
          {t.message}
        </div>
      ))}
    </div>
  )
}

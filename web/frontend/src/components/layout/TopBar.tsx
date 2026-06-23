import { useAppStore } from '../../store/appStore'

export function TopBar() {
  const tabTitle = useAppStore((s) => s.tabTitle)
  const connected = useAppStore((s) => s.connected)
  const providers = useAppStore((s) => s.providers)
  const currentModel = useAppStore((s) => s.currentModel)
  const theme = useAppStore((s) => s.theme)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)
  const toggleTheme = useAppStore((s) => s.toggleTheme)
  const switchModel = useAppStore((s) => s.switchModel)

  return (
    <header className="h-[52px] flex items-center justify-between px-6 border-b border-[var(--color-border)] bg-[var(--color-bg-surface)] shrink-0">
      <div className="flex items-center gap-4">
        <button className="md:hidden opacity-70 hover:opacity-100 text-lg" onClick={toggleSidebar}>
          ☰
        </button>
        <span className="font-[family-name:var(--font-mono)] text-[0.92rem] font-semibold">{tabTitle}</span>
      </div>

      <div className="flex items-center gap-3">
        <span className={`inline-block w-2 h-2 rounded-full ${connected ? 'bg-[var(--color-success)]' : 'bg-[var(--color-danger)]'}`} />
        <span className="text-xs text-[var(--color-text-secondary)] hidden sm:inline">
          {connected ? 'Connected' : 'Disconnected'}
        </span>

        <select
          className="text-xs px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)]"
          value={currentModel}
          onChange={(e) => switchModel(e.target.value)}
        >
          {Object.entries(providers).map(([name, p]) => (
            <option key={name} value={name}>
              {p.label}
            </option>
          ))}
        </select>

        <button
          className="opacity-70 hover:opacity-100 text-lg px-1"
          onClick={toggleTheme}
          title={theme === 'dark' ? 'Switch to light' : 'Switch to dark'}
        >
          {theme === 'dark' ? '☀' : '☾'}
        </button>
      </div>
    </header>
  )
}

import { useAppStore } from '../../store/appStore'
import type { TabId } from '../../types/api'

const NAV: { id: TabId; icon: string; label: string; badge?: boolean }[] = [
  { id: 'overview', icon: '◈', label: 'Overview' },
  { id: 'chat', icon: '✦', label: 'Chat' },
  { id: 'agents', icon: '◆', label: 'Agents', badge: true },
  { id: 'sessions', icon: '◉', label: 'Sessions' },
  { id: 'tools', icon: '⬡', label: 'Tools' },
  { id: 'skills', icon: '⬢', label: 'Skills' },
  { id: 'plugins', icon: '⎔', label: 'Plugins' },
  { id: 'memory', icon: '◴', label: 'Memory' },
  { id: 'settings', icon: '⚙', label: 'Settings' },
  { id: 'config', icon: '⏣', label: 'Config' },
]

export function Sidebar() {
  const tab = useAppStore((s) => s.tab)
  const setTab = useAppStore((s) => s.setTab)
  const sidebarOpen = useAppStore((s) => s.sidebarOpen)
  const toggleSidebar = useAppStore((s) => s.toggleSidebar)
  const agentCount = useAppStore((s) => (s.status.agents || []).length)

  return (
    <aside
      className={`w-[220px] shrink-0 flex flex-col border-r border-[var(--color-border)] bg-[var(--color-bg-surface)] z-10 transition-transform max-md:fixed max-md:inset-y-0 max-md:left-0 ${sidebarOpen ? 'max-md:translate-x-0' : 'max-md:-translate-x-full'}`}
    >
      <div className="h-[52px] flex items-center gap-2 px-5 border-b border-[var(--color-border-muted)]">
        <span className="font-[family-name:var(--font-mono)] text-lg font-bold text-[var(--color-accent)] tracking-tight">
          CktClaw
        </span>
        <span className="text-[0.72rem] text-[var(--color-text-dim)] font-[family-name:var(--font-mono)]">v2</span>
      </div>

      <nav className="flex-1 overflow-y-auto py-2 px-2">
        {NAV.slice(0, 4).map((item) => (
          <NavButton key={item.id} item={item} active={tab === item.id} onClick={() => setTab(item.id)} badge={item.badge ? agentCount : undefined} />
        ))}
        <div className="my-2 mx-3 border-t border-[var(--color-border-muted)]" />
        {NAV.slice(4, 8).map((item) => (
          <NavButton key={item.id} item={item} active={tab === item.id} onClick={() => setTab(item.id)} />
        ))}
        <div className="my-2 mx-3 border-t border-[var(--color-border-muted)]" />
        {NAV.slice(8).map((item) => (
          <NavButton key={item.id} item={item} active={tab === item.id} onClick={() => setTab(item.id)} />
        ))}
      </nav>

      <div className="px-3 py-2 border-t border-[var(--color-border-muted)] text-[0.72rem] text-[var(--color-text-dim)] flex items-center justify-between">
        <span>CktClaw v2 · Jingxin Wang</span>
        <button className="md:hidden opacity-60 hover:opacity-100" onClick={toggleSidebar}>
          ☰
        </button>
      </div>
    </aside>
  )
}

function NavButton({
  item,
  active,
  onClick,
  badge,
}: {
  item: (typeof NAV)[0]
  active: boolean
  onClick: () => void
  badge?: number
}) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-sm mb-0.5 transition-colors cursor-pointer border-none text-left ${
        active
          ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)] font-medium'
          : 'text-[var(--color-text-secondary)] hover:bg-[var(--color-bg-overlay)] hover:text-[var(--color-text)] bg-transparent'
      }`}
    >
      <span className="w-[18px] text-center shrink-0">{item.icon}</span>
      <span>{item.label}</span>
      {badge !== undefined && (
        <span
          className={`ml-auto text-[0.72rem] px-1.5 py-px rounded-lg font-[family-name:var(--font-mono)] min-w-[20px] text-center ${
            active ? 'bg-[var(--color-accent)] text-white' : 'bg-[var(--color-bg-overlay)] text-[var(--color-text-dim)]'
          }`}
        >
          {badge}
        </span>
      )}
    </button>
  )
}

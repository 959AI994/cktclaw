import { useEffect } from 'react'
import { Sidebar } from './components/layout/Sidebar'
import { TopBar } from './components/layout/TopBar'
import { ToastContainer } from './components/ui/Toast'
import { OverviewPanel } from './components/panels/OverviewPanel'
import { ChatPanel } from './components/panels/ChatPanel'
import { AgentsPanel } from './components/panels/AgentsPanel'
import { SessionsPanel } from './components/panels/SessionsPanel'
import { ToolsPanel } from './components/panels/ToolsPanel'
import { SkillsPanel } from './components/panels/SkillsPanel'
import { PluginsPanel } from './components/panels/PluginsPanel'
import { MemoryPanel } from './components/panels/MemoryPanel'
import { SettingsPanel } from './components/panels/SettingsPanel'
import { ConfigPanel } from './components/panels/ConfigPanel'
import { useAppStore } from './store/appStore'
import { useWebSocket } from './hooks/useWebSocket'
import type { TabId } from './types/api'

const TABS: TabId[] = ['overview', 'chat', 'agents', 'sessions', 'tools', 'skills', 'plugins', 'memory', 'settings', 'config']

function App() {
  const tab = useAppStore((s) => s.tab)
  const setTab = useAppStore((s) => s.setTab)
  const applyTheme = useAppStore((s) => s.applyTheme)
  const fetchProviders = useAppStore((s) => s.fetchProviders)
  const fetchOverview = useAppStore((s) => s.fetchOverview)
  const loadTab = useAppStore((s) => s.loadTab)
  const setShowSpawn = useAppStore((s) => s.setShowSpawn)
  const setShowInstall = useAppStore((s) => s.setShowInstall)

  useWebSocket()

  useEffect(() => {
    applyTheme()
    fetchProviders()
    fetchOverview()
    loadTab(tab)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const interval = setInterval(() => {
      if (useAppStore.getState().tab === 'overview') {
        fetchOverview()
      }
    }, 15000)
    return () => clearInterval(interval)
  }, [fetchOverview])

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement
      if (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT') return

      const num = parseInt(e.key)
      if (num >= 1 && num <= TABS.length) {
        setTab(TABS[num - 1])
        return
      }
      if (e.key === 'Escape') {
        setShowSpawn(false)
        setShowInstall(false)
      }
      if (e.key === '?' || (e.key === 'h' && e.shiftKey)) {
        alert('Shortcuts:\n1-0 Switch tabs\n/ Search\nEsc Close modal\n? Help')
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [setTab, setShowSpawn, setShowInstall])

  return (
    <div className="flex h-full overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        <TopBar />
        <main className="flex-1 overflow-y-auto p-5">
          {tab === 'overview' && <OverviewPanel />}
          {tab === 'chat' && <ChatPanel />}
          {tab === 'agents' && <AgentsPanel />}
          {tab === 'sessions' && <SessionsPanel />}
          {tab === 'tools' && <ToolsPanel />}
          {tab === 'skills' && <SkillsPanel />}
          {tab === 'plugins' && <PluginsPanel />}
          {tab === 'memory' && <MemoryPanel />}
          {tab === 'settings' && <SettingsPanel />}
          {tab === 'config' && <ConfigPanel />}
        </main>
      </div>
      <ToastContainer />
    </div>
  )
}

export default App

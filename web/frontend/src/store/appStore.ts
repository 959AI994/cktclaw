import { create } from 'zustand'
import type {
  AgentInfo,
  AgentsSubTab,
  ChipProgressEvent,
  MemoryEntry,
  MemorySearchResult,
  OrchestratorRun,
  UploadMeta,
  PluginInfo,
  ProviderInfo,
  SessionInfo,
  SessionMemoryEntry,
  SkillInfo,
  SkillStats,
  SystemEvent,
  SystemStatus,
  TabId,
  Toast,
  ToastLevel,
  ToolInfo,
} from '../types/api'
import { fetchJSON, postJSON } from '../lib/api'

const TAB_TITLES: Record<TabId, string> = {
  overview: 'Dashboard Overview',
  chat: 'Chat',
  agents: 'Agents',
  sessions: 'Sessions',
  tools: 'Tools',
  skills: 'Skills',
  plugins: 'Plugins',
  memory: 'Semantic Memory',
  settings: 'Settings',
  config: 'Raw Config',
}

function mergeProgressEvents(
  local?: ChipProgressEvent[],
  incoming?: ChipProgressEvent[],
): ChipProgressEvent[] {
  const merged = [...(local || []), ...(incoming || [])]
  const seen = new Set<string>()
  const result: ChipProgressEvent[] = []
  for (const evt of merged) {
    const key = [
      evt.timestamp || '',
      evt.event_type || '',
      evt.phase || '',
      evt.skill || '',
      evt.status || '',
      evt.message || '',
    ].join('|')
    if (seen.has(key)) continue
    seen.add(key)
    result.push(evt)
  }
  return result.slice(-300)
}

interface AppState {
  tab: TabId
  tabTitle: string
  connected: boolean
  sidebarOpen: boolean
  theme: 'dark' | 'light'
  status: SystemStatus
  providers: Record<string, ProviderInfo>
  currentModel: string
  toasts: Toast[]
  events: SystemEvent[]

  agents: AgentInfo[]
  sessions: SessionInfo[]
  tools: ToolInfo[]
  toolsLoading: boolean
  toolsError: string | null
  skills: SkillInfo[]
  skillsLoading: boolean
  skillsError: string | null
  skillStats: SkillStats
  plugins: PluginInfo[]
  pluginsLoading: boolean
  memoryEntries: MemoryEntry[]
  memoryNote: string | null
  embeddingsAvailable: boolean | null
  embeddingBackend: string | null
  embeddingModel: string | null
  embeddingErrorDetail: string | null
  missingDependency: string | null
  memoryWarmingUp: boolean
  memorySources: { vector?: number; session?: number }
  sessionMemoryEntries: SessionMemoryEntry[]
  allSessionMemoryEntries: SessionMemoryEntry[]
  memResults: MemorySearchResult[]
  memQuery: string
  configText: string

  showSpawn: boolean
  showInstall: boolean
  agentsSubTab: AgentsSubTab
  spawnForm: { name: string; task: string; system_prompt: string; model: string }
  spawnAttachments: UploadMeta[]
  agentUploadSessionId: string
  orchestratorForm: { skill: string; task: string; session_id: string }
  orchestratorAttachments: UploadMeta[]
  orchestratorUploadSessionId: string
  orchestratorRuns: OrchestratorRun[]
  installForm: { source_path: string; git_url: string }

  setTab: (tab: TabId) => void
  setConnected: (v: boolean) => void
  toggleSidebar: () => void
  toggleTheme: () => void
  applyTheme: () => void
  toast: (level: ToastLevel, message: string) => void
  removeToast: (id: number) => void
  addEvent: (event_type: string, data: unknown, timestamp?: string) => void

  fetchOverview: () => Promise<void>
  fetchProviders: () => Promise<void>
  fetchAgents: () => Promise<void>
  fetchSessions: () => Promise<void>
  fetchTools: () => Promise<void>
  fetchSkills: () => Promise<void>
  fetchPlugins: () => Promise<void>
  fetchMemory: () => Promise<void>
  warmupMemory: () => Promise<void>
  fetchSessionMemory: (sessionId: string) => Promise<void>
  fetchAllSessionMemories: () => Promise<void>
  saveSessionMemory: (payload: {
    session_id: string
    topic: string
    summary: string
    content: string
    memory_type?: string
  }) => Promise<void>
  fetchConfig: () => Promise<void>
  searchMemory: () => Promise<void>
  setMemQuery: (q: string) => void

  spawnAgent: () => Promise<void>
  stopAgent: (id: string) => Promise<void>
  viewAgent: (id: string) => Promise<void>
  fetchOrchestratorRuns: () => Promise<void>
  runOrchestrator: () => Promise<void>
  abortOrchestrator: (runId: string) => Promise<void>
  handleOrchestratorWsEvent: (eventType: string, data: unknown) => void
  setAgentsSubTab: (tab: AgentsSubTab) => void
  setOrchestratorForm: (f: Partial<AppState['orchestratorForm']>) => void
  deleteSession: (id: string) => Promise<void>
  viewSession: (id: string) => Promise<void>
  installPlugin: () => Promise<void>
  reloadPlugins: () => Promise<void>
  saveProvider: (name: string, updates: { api_key?: string; base_url?: string; model?: string }) => Promise<void>
  switchModel: (provider: string) => Promise<void>
  saveConfig: () => Promise<void>
  setShowSpawn: (v: boolean) => void
  setShowInstall: (v: boolean) => void
  setSpawnForm: (f: Partial<AppState['spawnForm']>) => void
  setSpawnAttachments: (attachments: UploadMeta[]) => void
  setOrchestratorAttachments: (attachments: UploadMeta[]) => void
  setInstallForm: (f: Partial<AppState['installForm']>) => void
  setConfigText: (t: string) => void
  loadTab: (tab: TabId) => void
}

export const useAppStore = create<AppState>((set, get) => ({
  tab: (localStorage.getItem('cktclaw-tab') as TabId) || 'overview',
  tabTitle: TAB_TITLES[(localStorage.getItem('cktclaw-tab') as TabId) || 'overview'],
  connected: false,
  sidebarOpen: true,
  theme: (localStorage.getItem('cktclaw-theme') as 'dark' | 'light') || 'dark',
  status: {},
  providers: {},
  currentModel: '',
  toasts: [],
  events: [],

  agents: [],
  sessions: [],
  tools: [],
  toolsLoading: false,
  toolsError: null,
  skills: [],
  skillsLoading: false,
  skillsError: null,
  skillStats: {},
  plugins: [],
  pluginsLoading: false,
  memoryEntries: [],
  memoryNote: null,
  embeddingsAvailable: null,
  embeddingBackend: null,
  embeddingModel: null,
  embeddingErrorDetail: null,
  missingDependency: null,
  memoryWarmingUp: false,
  memorySources: {},
  sessionMemoryEntries: [],
  allSessionMemoryEntries: [],
  memResults: [],
  memQuery: '',
  configText: '',

  showSpawn: false,
  showInstall: false,
  agentsSubTab: 'worker',
  spawnForm: { name: '', task: '', system_prompt: '', model: '' },
  spawnAttachments: [],
  agentUploadSessionId: '',
  orchestratorForm: { skill: 'chip-rtl', task: '', session_id: '' },
  orchestratorAttachments: [],
  orchestratorUploadSessionId: '',
  orchestratorRuns: [],
  installForm: { source_path: '', git_url: '' },

  setTab: (tab) => {
    localStorage.setItem('cktclaw-tab', tab)
    set({ tab, tabTitle: TAB_TITLES[tab] })
    get().loadTab(tab)
  },

  setConnected: (connected) => set({ connected }),

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),

  toggleTheme: () => {
    const theme = get().theme === 'dark' ? 'light' : 'dark'
    localStorage.setItem('cktclaw-theme', theme)
    set({ theme })
    get().applyTheme()
  },

  applyTheme: () => {
    document.documentElement.setAttribute('data-theme', get().theme)
  },

  toast: (level, message) => {
    const id = Date.now() + Math.random()
    set((s) => ({ toasts: [...s.toasts, { id, level, message }] }))
    setTimeout(() => get().removeToast(id), 3500)
  },

  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),

  addEvent: (event_type, data, timestamp) => {
    set((s) => ({
      events: [{ event_type, data, timestamp }, ...s.events].slice(0, 300),
    }))
  },

  fetchOverview: async () => {
    try {
      const status = await fetchJSON<SystemStatus>('/api/status')
      status.agents = status.agents || []
      set({ status })
    } catch {
      set({ status: {} })
    }
  },

  fetchProviders: async () => {
    try {
      const d = await fetchJSON<{ providers?: Record<string, ProviderInfo> }>('/api/models/providers')
      const providers = d.providers || {}
      const cur = Object.entries(providers).find(([, v]) => v.is_current)
      set({ providers, currentModel: cur ? cur[0] : '' })
    } catch {
      set({ providers: {} })
    }
  },

  fetchAgents: async () => {
    try {
      const agents = await fetchJSON<AgentInfo[]>('/api/agents')
      set({ agents: agents || [] })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchSessions: async () => {
    try {
      const sessions = await fetchJSON<SessionInfo[]>('/api/sessions')
      set({ sessions: sessions || [] })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchTools: async () => {
    set({ toolsLoading: true, toolsError: null })
    try {
      const tools = await fetchJSON<ToolInfo[]>('/api/tools')
      set({ tools: tools || [], toolsLoading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed'
      set({ toolsLoading: false, toolsError: msg })
      get().toast('error', msg)
    }
  },

  fetchSkills: async () => {
    set({ skillsLoading: true, skillsError: null })
    try {
      const [skills, stats] = await Promise.all([
        fetchJSON<SkillInfo[]>('/api/skills'),
        fetchJSON<SkillStats>('/api/skills/stats'),
      ])
      set({ skills: skills || [], skillStats: stats, skillsLoading: false })
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed'
      set({ skillsLoading: false, skillsError: msg })
      get().toast('error', msg)
    }
  },

  fetchPlugins: async () => {
    set({ pluginsLoading: true })
    try {
      const plugins = await fetchJSON<PluginInfo[]>('/api/plugins')
      set({ plugins: plugins || [], pluginsLoading: false })
    } catch (e) {
      set({ pluginsLoading: false })
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchMemory: async () => {
    try {
      const d = await fetchJSON<{
        entries?: MemoryEntry[]
        note?: string
        embeddings_available?: boolean
        embedding_backend?: string
        embedding_model?: string
        error_detail?: string
        missing_dependency?: string
        sources?: { vector?: number; session?: number }
      }>('/api/memory')
      set({
        memoryEntries: d.entries || [],
        memoryNote: d.note || null,
        embeddingsAvailable: d.embeddings_available ?? null,
        embeddingBackend: d.embedding_backend || null,
        embeddingModel: d.embedding_model || null,
        embeddingErrorDetail: d.error_detail || null,
        missingDependency: d.missing_dependency || null,
        memorySources: d.sources || {},
      })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  warmupMemory: async () => {
    set({ memoryWarmingUp: true })
    try {
      const d = await postJSON<{
        status?: string
        available?: boolean
        note?: string
        error_detail?: string
        missing_dependency?: string
        embedding_backend?: string
        embedding_model?: string
        backend?: string
        model?: string
      }>('/api/memory/warmup', {})
      set({
        memoryWarmingUp: false,
        embeddingsAvailable: d.available ?? null,
        embeddingBackend: d.embedding_backend || d.backend || null,
        embeddingModel: d.embedding_model || d.model || null,
        embeddingErrorDetail: d.error_detail || null,
        missingDependency: d.missing_dependency || null,
        memoryNote: d.note || null,
      })
      if (d.available) {
        get().toast('success', 'Embedding model ready')
        await get().fetchMemory()
      } else {
        get().toast('error', d.error_detail || d.note || 'Warmup failed')
      }
    } catch (e) {
      set({ memoryWarmingUp: false })
      get().toast('error', e instanceof Error ? e.message : 'Warmup failed')
    }
  },

  fetchSessionMemory: async (sessionId) => {
    if (!sessionId) {
      set({ sessionMemoryEntries: [] })
      return
    }
    try {
      const d = await fetchJSON<{ entries?: SessionMemoryEntry[] }>(
        `/api/memory/session?session_id=${encodeURIComponent(sessionId)}`,
      )
      set({ sessionMemoryEntries: d.entries || [] })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchAllSessionMemories: async () => {
    try {
      const d = await fetchJSON<{ entries?: SessionMemoryEntry[] }>('/api/memory/session/all')
      set({ allSessionMemoryEntries: d.entries || [] })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  saveSessionMemory: async (payload) => {
    try {
      const d = await postJSON<{ status?: string; error?: string }>('/api/memory/session', payload)
      if (d.status === 'saved') {
        get().toast('success', 'Session memory saved')
        await get().fetchSessionMemory(payload.session_id)
        await get().fetchAllSessionMemories()
        await get().fetchMemory()
      } else {
        get().toast('error', d.error || 'Save failed')
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchConfig: async () => {
    try {
      const d = await fetchJSON<unknown>('/api/config')
      const configText = typeof d === 'string' ? d : JSON.stringify(d, null, 2)
      set({ configText })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  searchMemory: async () => {
    const query = get().memQuery.trim()
    if (!query) return
    try {
      const d = await postJSON<{ results?: MemorySearchResult[]; note?: string }>('/api/memory/search', {
        query,
        top_k: 10,
      })
      set({ memResults: d.results || [] })
      if (d.note && !d.results?.length) {
        get().toast('error', d.note)
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  setMemQuery: (memQuery) => set({ memQuery }),

  spawnAgent: async () => {
    const { spawnForm, spawnAttachments, agentUploadSessionId } = get()
    const task = spawnForm.task.trim()
    if (!task) {
      get().toast('error', 'Task is required')
      return
    }
    const uploadSession = agentUploadSessionId || `web-agent-${Date.now().toString(36)}`
    try {
      await postJSON<{ agent_id: string; status: string }>('/api/agents', {
        name: spawnForm.name || 'web-agent',
        task,
        system_prompt: spawnForm.system_prompt || null,
        model: spawnForm.model || null,
        session_id: uploadSession,
        attachment_ids: spawnAttachments.map((a) => a.id),
      })
      set({
        showSpawn: false,
        spawnForm: { name: '', task: '', system_prompt: '', model: '' },
        spawnAttachments: [],
        agentUploadSessionId: '',
      })
      get().toast('success', 'Agent spawned')
      get().fetchAgents()
      get().fetchOverview()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  stopAgent: async (id) => {
    if (!confirm(`Stop agent ${id}?`)) return
    try {
      await postJSON('/api/agents/' + encodeURIComponent(id) + '/stop', {})
      get().toast('info', 'Stop requested')
      get().fetchAgents()
      get().fetchOverview()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  viewAgent: async (id) => {
    try {
      const d = await fetchJSON<unknown>(`/api/agents/${id}`)
      alert(JSON.stringify(d, null, 2))
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  fetchOrchestratorRuns: async () => {
    try {
      const runs = await fetchJSON<OrchestratorRun[]>('/api/orchestrator/runs')
      set((s) => {
        const apiRuns = runs || []
        const merged = apiRuns.map((apiRun) => {
          const local = s.orchestratorRuns.find((r) => r.run_id === apiRun.run_id)
          if (!local) return apiRun
          return {
            ...apiRun,
            logs: (local.logs?.length ? local.logs : apiRun.logs) || [],
            current_stage: apiRun.current_stage || local.current_stage,
            stage_index: apiRun.stage_index || local.stage_index,
            stage_total: apiRun.stage_total || local.stage_total,
            status: apiRun.status || local.status,
            intent: apiRun.intent || local.intent,
            route_rationale: apiRun.route_rationale || local.route_rationale,
            progress_events: mergeProgressEvents(local.progress_events, apiRun.progress_events),
            agent_plan: apiRun.agent_plan?.length ? apiRun.agent_plan : local.agent_plan,
            artifact_index: apiRun.artifact_index?.length ? apiRun.artifact_index : local.artifact_index,
            qor_summary: Object.keys(apiRun.qor_summary || {}).length ? apiRun.qor_summary : local.qor_summary,
            coverage_summary: Object.keys(apiRun.coverage_summary || {}).length
              ? apiRun.coverage_summary
              : local.coverage_summary,
            fix_requests: apiRun.fix_requests?.length ? apiRun.fix_requests : local.fix_requests,
          }
        })
        for (const local of s.orchestratorRuns) {
          if (!merged.some((r) => r.run_id === local.run_id)) {
            merged.unshift(local)
          }
        }
        return { orchestratorRuns: merged }
      })
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed to load orchestrator runs')
    }
  },

  runOrchestrator: async () => {
    const { orchestratorForm, orchestratorAttachments, orchestratorUploadSessionId } = get()
    const task = orchestratorForm.task.trim()
    if (!task) {
      get().toast('error', 'Task is required')
      return
    }
    if (!orchestratorForm.skill) {
      get().toast('error', 'Select a chip specialist skill')
      return
    }
    const uploadSession = orchestratorUploadSessionId || orchestratorForm.session_id || `web-orch-${Date.now().toString(36)}`
    try {
      const res = await postJSON<{ run_id: string; status: string }>('/api/orchestrator/run', {
        skill: orchestratorForm.skill,
        task,
        session_id: uploadSession,
        auto_confirm: true,
        attachment_ids: orchestratorAttachments.map((a) => a.id),
      })
      get().toast('success', `Orchestrator started (${res.run_id})`)
      set({
        orchestratorForm: { ...orchestratorForm, task: '' },
        orchestratorAttachments: [],
      })
      await get().fetchOrchestratorRuns()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed to start orchestrator')
    }
  },

  abortOrchestrator: async (runId) => {
    if (!confirm(`Abort orchestrator run ${runId}?`)) return
    try {
      await postJSON(`/api/orchestrator/runs/${encodeURIComponent(runId)}/abort`, {})
      get().toast('info', 'Abort requested')
      get().fetchOrchestratorRuns()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed to abort')
    }
  },

  handleOrchestratorWsEvent: (eventType, data) => {
    const payload = (data || {}) as Partial<OrchestratorRun> & ChipProgressEvent & { run_id?: string; stage?: string; index?: number; total?: number; message?: string; error?: string }
    const runId = payload.run_id
    if (!runId) return

    set((s) => {
      const runs = [...s.orchestratorRuns]
      let idx = runs.findIndex((r) => r.run_id === runId)
      if (idx < 0) {
        runs.unshift({
          run_id: runId,
          skill: (payload as { skill?: string }).skill || '?',
          task: (payload as { task?: string }).task || '',
          status: 'running',
          logs: [],
        })
        idx = 0
      }
      const run = { ...runs[idx] }
      if (eventType.startsWith('chip_progress:')) {
        const progress = payload as ChipProgressEvent
        run.progress_events = mergeProgressEvents(run.progress_events, [progress])
        run.current_stage = progress.phase || progress.skill || run.current_stage
        run.stage_index = progress.index ?? run.stage_index
        run.stage_total = progress.total ?? run.stage_total
        if (progress.event_type === 'run_completed') run.status = 'completed'
        else if (progress.event_type === 'run_failed') run.status = 'failed'
        else if (progress.event_type?.includes('started') || progress.event_type?.includes('running')) {
          run.status = 'running'
        }
        const agentPlan = progress.metadata?.agent_plan
        if (Array.isArray(agentPlan)) run.agent_plan = agentPlan
        if (progress.artifacts?.length) {
          run.artifact_index = Array.from(new Set([...(run.artifact_index || []), ...progress.artifacts])).slice(-100)
        }
        if (progress.qor && Object.keys(progress.qor).length) run.qor_summary = progress.qor
        if (progress.coverage && Object.keys(progress.coverage).length) run.coverage_summary = progress.coverage
        if (progress.fix_request) run.fix_requests = [...(run.fix_requests || []), progress.fix_request].slice(-50)
        if (progress.message) {
          const label = progress.phase || progress.skill || progress.event_type
          run.logs = [...(run.logs || []), `[${label}] ${progress.message}`].slice(-50)
        }
      } else if (eventType === 'orchestrator:started') {
        run.status = 'running'
      } else if (eventType === 'orchestrator:stage_start') {
        run.current_stage = payload.stage
        run.stage_index = payload.index
        run.stage_total = payload.total
        run.status = 'running'
      } else if (eventType === 'orchestrator:log' && payload.message) {
        run.logs = [...(run.logs || []), payload.message].slice(-50)
      } else if (eventType === 'orchestrator:done') {
        run.status = 'completed'
      } else if (eventType === 'orchestrator:failed') {
        run.status = run.status === 'aborted' ? 'aborted' : 'failed'
        run.error = payload.error
      }
      runs[idx] = run
      return { orchestratorRuns: runs }
    })
  },

  setAgentsSubTab: (agentsSubTab) => {
    const patch: Partial<AppState> = { agentsSubTab }
    if (agentsSubTab === 'specialist' && !get().orchestratorUploadSessionId) {
      patch.orchestratorUploadSessionId = `web-orch-${Date.now().toString(36)}`
    }
    set(patch)
    if (agentsSubTab === 'specialist') {
      get().fetchSkills()
      get().fetchOrchestratorRuns()
    }
  },

  setSpawnAttachments: (spawnAttachments) => set({ spawnAttachments }),
  setOrchestratorAttachments: (orchestratorAttachments) => set({ orchestratorAttachments }),

  setOrchestratorForm: (f) => set((s) => ({ orchestratorForm: { ...s.orchestratorForm, ...f } })),

  deleteSession: async (id) => {
    if (!confirm(`Delete session ${id}?`)) return
    try {
      await fetch(`/api/sessions/${id}`, { method: 'DELETE' })
      get().toast('info', 'Deleted')
      get().fetchSessions()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  viewSession: async (id) => {
    try {
      const msgs = await fetchJSON<{ role?: string; content?: string }[]>(
        `/api/sessions/${id}/messages?limit=30`,
      )
      const text = msgs.map((m) => `[${m.role || '?'}] ${m.content || ''}`).join('\n\n---\n\n')
      const w = window.open('', '_blank', 'width=800,height=600')
      if (w) {
        w.document.write(
          `<pre style="background:#0d1117;color:#e6edf3;padding:1.5rem;font-family:monospace;font-size:0.82rem;white-space:pre-wrap;line-height:1.5">${text.replace(/</g, '&lt;')}</pre>`,
        )
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  installPlugin: async () => {
    const { installForm } = get()
    const body: Record<string, string> = {}
    if (installForm.git_url) body.git_url = installForm.git_url
    else if (installForm.source_path) body.source_path = installForm.source_path
    else {
      get().toast('error', 'Provide a path or Git URL')
      return
    }
    try {
      const res = await fetch('/api/plugins/install', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        set({ showInstall: false, installForm: { source_path: '', git_url: '' } })
        get().toast('success', 'Installed')
        get().fetchPlugins()
      } else {
        const e = await res.json()
        get().toast('error', e.detail || 'Failed')
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  reloadPlugins: async () => {
    try {
      await fetch('/api/plugins/reload', { method: 'POST' })
      get().toast('success', 'Reloaded')
      get().fetchPlugins()
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  saveProvider: async (name, updates) => {
    if (!Object.keys(updates).length) {
      get().toast('error', 'No changes to save')
      return
    }
    try {
      const res = await fetch('/api/models/update-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider: name, ...updates }),
      })
      if (res.ok) {
        get().toast('success', `${name} config saved`)
        await get().fetchProviders()
      } else {
        const e = await res.json()
        get().toast('error', e.detail || 'Save failed')
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  switchModel: async (provider) => {
    try {
      const res = await fetch('/api/models/switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider }),
      })
      if (res.ok) {
        get().toast('success', `Switched to ${provider}`)
        set({ currentModel: provider })
        await get().fetchProviders()
        get().fetchOverview()
      } else {
        const e = await res.json()
        get().toast('error', e.detail || 'Switch failed. Set the API key first.')
      }
    } catch (e) {
      get().toast('error', e instanceof Error ? e.message : 'Failed')
    }
  },

  saveConfig: async () => {
    try {
      const json = JSON.parse(get().configText)
      await fetch('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(json),
      })
      get().toast('success', 'Config saved')
    } catch (e) {
      get().toast('error', `Invalid JSON or save failed: ${e instanceof Error ? e.message : 'unknown'}`)
    }
  },

  setShowSpawn: (showSpawn) => {
    if (showSpawn && !get().agentUploadSessionId) {
      set({ showSpawn, agentUploadSessionId: `web-agent-${Date.now().toString(36)}`, spawnAttachments: [] })
    } else if (!showSpawn) {
      set({ showSpawn, spawnAttachments: [], agentUploadSessionId: '' })
    } else {
      set({ showSpawn })
    }
  },
  setShowInstall: (showInstall) => set({ showInstall }),
  setSpawnForm: (f) => set((s) => ({ spawnForm: { ...s.spawnForm, ...f } })),
  setInstallForm: (f) => set((s) => ({ installForm: { ...s.installForm, ...f } })),
  setConfigText: (configText) => set({ configText }),

  loadTab: (tab) => {
    const loaders: Partial<Record<TabId, () => void>> = {
      overview: () => {
        get().fetchOverview()
        get().fetchSkills()
      },
      agents: () => {
        get().fetchAgents()
        get().fetchOrchestratorRuns()
      },
      sessions: () => get().fetchSessions(),
      tools: () => get().fetchTools(),
      skills: () => get().fetchSkills(),
      plugins: () => get().fetchPlugins(),
      memory: () => get().fetchMemory(),
      settings: () => get().fetchProviders(),
      config: () => get().fetchConfig(),
    }
    loaders[tab]?.()
  },
}))

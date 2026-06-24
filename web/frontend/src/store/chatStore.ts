import { create } from 'zustand'
import type {
  ActiveOrchestratorRun,
  ChatAttachmentRef,
  ChatMessage,
  OrchestratorProposal,
  SessionInfo,
  ToolCallInfo,
  UploadMeta,
  WsChatMessage,
} from '../types/api'
import { fetchJSON } from '../lib/api'

const MAX_RUN_LOGS = 30

interface ChatState {
  sessionId: string
  availableSessions: SessionInfo[]
  sessionsLoading: boolean
  messages: ChatMessage[]
  inputText: string
  pendingAttachments: UploadMeta[]
  streamBuffer: string
  streaming: boolean
  useTools: boolean
  skipOrchestratorConfirm: boolean
  disableTools: boolean
  orchestratorProposal: OrchestratorProposal | null
  activeOrchestratorRun: ActiveOrchestratorRun | null
  pendingToolCalls: Record<string, ToolCallInfo>

  setSessionId: (id: string) => void
  setInputText: (t: string) => void
  setUseTools: (v: boolean) => void
  setSkipOrchestratorConfirm: (v: boolean) => void
  setDisableTools: (v: boolean) => void
  setPendingAttachments: (attachments: UploadMeta[]) => void
  addPendingAttachments: (attachments: UploadMeta[]) => void
  removePendingAttachment: (id: string) => void
  clearPendingAttachments: () => void
  fetchAvailableSessions: () => Promise<void>
  initChat: () => Promise<void>
  loadSession: () => Promise<void>
  newSession: () => void
  sendMessage: (
    sendChat: (
      sessionId: string,
      message: string,
      opts: { skipOrchestratorConfirm: boolean; disableTools: boolean },
      attachmentIds?: string[],
    ) => void,
  ) => void
  abortChat: (abortChat: (sessionId: string) => void) => void
  confirmOrchestrator: (
    confirmFn: (sessionId: string, skill: string, task: string, attachmentIds?: string[]) => void,
    task?: string,
  ) => void
  cancelOrchestrator: (
    cancelFn: (sessionId: string, task: string, opts: { disableTools: boolean }, attachmentIds?: string[]) => void,
  ) => void
  handleChatMessage: (msg: WsChatMessage) => void
  reset: () => void
}

function mapRole(role?: string): 'user' | 'assistant' {
  const r = (role || '').toLowerCase()
  if (r === 'assistant' || r === 'tool') return 'assistant'
  if (r === 'system') return 'assistant'
  return 'user'
}

function toAttachmentRefs(attachments: UploadMeta[]): ChatAttachmentRef[] {
  return attachments.map((a) => ({
    id: a.id,
    filename: a.filename,
    mime: a.mime,
    url: a.url,
    session_id: a.session_id,
  }))
}

function mergeRunProgress(
  existing: ActiveOrchestratorRun | null,
  msg: WsChatMessage,
): ActiveOrchestratorRun {
  const runId = msg.run_id || existing?.run_id || ''
  const logs = [...(existing?.logs || [])]
  if (msg.logs_tail?.length) {
    return {
      run_id: runId,
      skill: msg.skill || existing?.skill || '?',
      task: msg.task || existing?.task,
      status: (msg.status as ActiveOrchestratorRun['status']) || existing?.status || 'running',
      stage: msg.stage ?? existing?.stage,
      stage_index: msg.stage_index ?? existing?.stage_index,
      stage_total: msg.stage_total ?? existing?.stage_total,
      logs: msg.logs_tail.slice(-MAX_RUN_LOGS),
      error: existing?.error,
      summary: existing?.summary,
    }
  }
  if (msg.log_delta) {
    logs.push(msg.log_delta)
  }
  return {
    run_id: runId,
    skill: msg.skill || existing?.skill || '?',
    task: msg.task || existing?.task,
    status: (msg.status as ActiveOrchestratorRun['status']) || existing?.status || 'running',
    stage: msg.stage ?? existing?.stage,
    stage_index: msg.stage_index ?? existing?.stage_index,
    stage_total: msg.stage_total ?? existing?.stage_total,
    logs: logs.slice(-MAX_RUN_LOGS),
    error: existing?.error,
    summary: existing?.summary,
  }
}

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: '',
  availableSessions: [],
  sessionsLoading: false,
  messages: [],
  inputText: '',
  pendingAttachments: [],
  streamBuffer: '',
  streaming: false,
  useTools: true,
  skipOrchestratorConfirm: false,
  disableTools: false,
  orchestratorProposal: null,
  activeOrchestratorRun: null,
  pendingToolCalls: {},

  setSessionId: (sessionId) => {
    set({ sessionId, pendingAttachments: [], orchestratorProposal: null, activeOrchestratorRun: null })
    get().loadSession()
  },

  setInputText: (inputText) => set({ inputText }),
  setUseTools: (useTools) => set({ useTools }),
  setSkipOrchestratorConfirm: (skipOrchestratorConfirm) => set({ skipOrchestratorConfirm }),
  setDisableTools: (disableTools) => set({ disableTools }),
  setPendingAttachments: (pendingAttachments) => set({ pendingAttachments }),
  addPendingAttachments: (attachments) =>
    set((s) => ({ pendingAttachments: [...s.pendingAttachments, ...attachments] })),
  removePendingAttachment: (id) =>
    set((s) => ({ pendingAttachments: s.pendingAttachments.filter((a) => a.id !== id) })),
  clearPendingAttachments: () => set({ pendingAttachments: [] }),

  fetchAvailableSessions: async () => {
    set({ sessionsLoading: true })
    try {
      const sessions = await fetchJSON<SessionInfo[]>('/api/sessions?limit=50')
      set({ availableSessions: sessions || [], sessionsLoading: false })
    } catch {
      set({ availableSessions: [], sessionsLoading: false })
    }
  },

  initChat: async () => {
    await get().fetchAvailableSessions()
    const { sessionId, availableSessions } = get()
    if (sessionId) {
      await get().loadSession()
      return
    }
    let defaultId = ''
    try {
      const status = await fetchJSON<{ sessions?: { latest_id?: string } }>('/api/status')
      defaultId = status.sessions?.latest_id || ''
    } catch {
      /* ignore */
    }
    if (!defaultId && availableSessions.length) {
      defaultId = availableSessions[0].session_id || availableSessions[0].id || ''
    }
    if (defaultId) {
      set({ sessionId: defaultId })
      await get().loadSession()
    }
  },

  loadSession: async () => {
    const { sessionId } = get()
    if (!sessionId) {
      set({ messages: [], pendingAttachments: [], orchestratorProposal: null, activeOrchestratorRun: null })
      return
    }
    try {
      const msgs = await fetchJSON<{ role?: string; content?: string; tool_calls?: ToolCallInfo[] }[]>(
        `/api/sessions/${encodeURIComponent(sessionId)}/messages?limit=50`,
      )
      const messages: ChatMessage[] = msgs
        .filter((m) => (m.role || '').toLowerCase() !== 'system')
        .map((m) => ({
          role: mapRole(m.role),
          content: m.content || '',
          tool_calls: m.tool_calls || [],
        }))
      set({
        messages,
        streamBuffer: '',
        streaming: false,
        pendingToolCalls: {},
        pendingAttachments: [],
        orchestratorProposal: null,
        activeOrchestratorRun: null,
      })
    } catch {
      set({ messages: [], pendingAttachments: [], orchestratorProposal: null, activeOrchestratorRun: null })
    }
  },

  newSession: () => {
    const id = 'web-' + Date.now().toString(36)
    set((s) => ({
      sessionId: id,
      availableSessions: [{ session_id: id, id, message_count: 0 }, ...s.availableSessions],
      messages: [],
      pendingAttachments: [],
      streamBuffer: '',
      streaming: false,
      pendingToolCalls: {},
      orchestratorProposal: null,
      activeOrchestratorRun: null,
    }))
  },

  sendMessage: (sendChat) => {
    const { inputText, streaming, sessionId, skipOrchestratorConfirm, disableTools, pendingAttachments } = get()
    const text = inputText.trim()
    if ((!text && !pendingAttachments.length) || streaming || !sessionId) return

    const attachmentRefs = toAttachmentRefs(pendingAttachments)
    const attachmentIds = pendingAttachments.map((a) => a.id)

    set((s) => ({
      messages: [
        ...s.messages,
        {
          role: 'user',
          content: text || '(attachments)',
          tool_calls: [],
          attachments: attachmentRefs.length ? attachmentRefs : undefined,
        },
      ],
      inputText: '',
      pendingAttachments: [],
      streamBuffer: '',
      streaming: true,
      pendingToolCalls: {},
      orchestratorProposal: null,
      activeOrchestratorRun: null,
    }))
    sendChat(
      sessionId,
      text,
      { skipOrchestratorConfirm, disableTools },
      attachmentIds.length ? attachmentIds : undefined,
    )
  },

  abortChat: (abortChat) => {
    const { sessionId, streamBuffer } = get()
    if (!sessionId) return
    abortChat(sessionId)
    if (streamBuffer) {
      set((s) => ({
        messages: [...s.messages, { role: 'assistant', content: streamBuffer + ' [aborted]', tool_calls: [] }],
        streamBuffer: '',
        streaming: false,
        orchestratorProposal: null,
        activeOrchestratorRun: null,
      }))
    } else {
      set({ streaming: false, orchestratorProposal: null, activeOrchestratorRun: null })
    }
  },

  confirmOrchestrator: (confirmFn, taskOverride) => {
    const { sessionId, orchestratorProposal, pendingAttachments } = get()
    if (!sessionId || !orchestratorProposal) return
    const task = taskOverride ?? orchestratorProposal.task
    const attachmentIds = pendingAttachments.map((a) => a.id)
    set({ streaming: false, orchestratorProposal: null })
    confirmFn(sessionId, orchestratorProposal.skill, task, attachmentIds.length ? attachmentIds : undefined)
  },

  cancelOrchestrator: (cancelFn) => {
    const { sessionId, orchestratorProposal, disableTools } = get()
    if (!sessionId || !orchestratorProposal) return
    set({ streaming: true, orchestratorProposal: null, activeOrchestratorRun: null })
    cancelFn(sessionId, orchestratorProposal.task, { disableTools })
  },

  handleChatMessage: (msg) => {
    const type = msg.type

    if (type === 'chat:chunk') {
      set((s) => ({ streamBuffer: s.streamBuffer + (msg.delta || '') }))
    } else if (type === 'chat:content_replace') {
      set({ streamBuffer: msg.content || '' })
    } else if (type === 'chat:orchestrator_proposal') {
      set({
        orchestratorProposal: {
          proposal_id: msg.proposal_id || '',
          skill: msg.skill || '',
          task: msg.task || '',
          confidence: msg.confidence ?? 0,
          estimated_stages: msg.estimated_stages,
          estimated_minutes: msg.estimated_minutes,
          pipeline_label: msg.pipeline_label,
        },
        streaming: false,
        streamBuffer: '',
        activeOrchestratorRun: null,
      })
    } else if (type === 'chat:orchestrator_started') {
      set({
        activeOrchestratorRun: {
          run_id: msg.run_id || '',
          skill: msg.skill || '?',
          task: msg.task,
          status: 'running',
          logs: ['Orchestrator 已启动，正在初始化...'],
        },
        streaming: false,
        streamBuffer: '',
        orchestratorProposal: null,
      })
    } else if (type === 'chat:orchestrator_progress') {
      set((s) => ({
        activeOrchestratorRun: mergeRunProgress(s.activeOrchestratorRun, msg),
        streaming: false,
      }))
    } else if (type === 'chat:orchestrator_done') {
      const summary = msg.summary || '(Orchestrator completed with no summary)'
      const artifactLines = (msg.artifacts || [])
        .map((a) => `- \`${a.path}\` (${a.kind}${a.size != null ? `, ${a.size} B` : ''})`)
        .join('\n')
      const content =
        summary.startsWith('## Orchestrator') || summary.startsWith('## ')
          ? summary
          : `## Orchestrator 完成 — ${msg.skill || 'orchestrator'}\n\n${summary}`
      const withArtifacts =
        artifactLines && !summary.includes('**产物文件：**')
          ? `${content}\n\n**产物文件（Web）：**\n${artifactLines}`
          : content
      set((s) => ({
        activeOrchestratorRun: null,
        streaming: false,
        messages: [
          ...s.messages,
          {
            role: 'assistant' as const,
            content: withArtifacts,
            tool_calls: [],
          },
        ],
      }))
    } else if (type === 'chat:orchestrator_failed') {
      const errText = msg.error || 'unknown error'
      set((s) => ({
        activeOrchestratorRun: s.activeOrchestratorRun
          ? { ...s.activeOrchestratorRun, status: 'failed', error: errText }
          : {
              run_id: msg.run_id || '',
              skill: msg.skill || '?',
              status: 'failed',
              logs: [],
              error: errText,
            },
        streaming: false,
        messages: [
          ...s.messages,
          {
            role: 'assistant' as const,
            content: `**Orchestrator 失败** (\`${msg.skill}\` · \`${msg.run_id}\`)\n\n*${errText}*`,
            tool_calls: [],
          },
        ],
      }))
    } else if (type === 'chat:tool_call') {
      const tc = msg.tool_call || {}
      if (tc.id) {
        set((s) => ({
          pendingToolCalls: {
            ...s.pendingToolCalls,
            [tc.id!]: { id: tc.id, name: tc.name || '?', arguments: tc.arguments, result: null },
          },
        }))
      }
    } else if (type === 'chat:tool_result') {
      const tcId = msg.tool_call_id
      if (tcId) {
        set((s) => {
          const existing = s.pendingToolCalls[tcId]
          if (!existing) return s
          return {
            pendingToolCalls: {
              ...s.pendingToolCalls,
              [tcId]: { ...existing, result: msg.content || '' },
            },
          }
        })
      }
    } else if (type === 'chat:done') {
      set((s) => {
        if (s.orchestratorProposal) {
          return { streaming: false }
        }
        const toolCalls = Object.values(s.pendingToolCalls)
        const hasStream = s.streamBuffer.length > 0
        if (!hasStream && toolCalls.length === 0 && (msg.usage?.orchestrator || s.activeOrchestratorRun)) {
          return { streaming: false, pendingToolCalls: {} }
        }
        return {
          messages: hasStream || toolCalls.length
            ? [
                ...s.messages,
                {
                  role: 'assistant' as const,
                  content: s.streamBuffer || '(empty response)',
                  tool_calls: toolCalls,
                },
              ]
            : s.messages,
          streamBuffer: '',
          streaming: false,
          pendingToolCalls: {},
        }
      })
    } else if (type === 'chat:error') {
      set((s) => {
        const errText = msg.error || 'unknown'
        const content = s.streamBuffer
          ? s.streamBuffer + `\n\n*Error: ${errText}*`
          : `*Error: ${errText}*`
        return {
          messages: [...s.messages, { role: 'assistant', content, tool_calls: [] }],
          streamBuffer: '',
          streaming: false,
          pendingToolCalls: {},
          orchestratorProposal: null,
          activeOrchestratorRun: null,
        }
      })
    }
  },

  reset: () =>
    set({
      sessionId: '',
      availableSessions: [],
      messages: [],
      inputText: '',
      pendingAttachments: [],
      streamBuffer: '',
      streaming: false,
      pendingToolCalls: {},
      orchestratorProposal: null,
      activeOrchestratorRun: null,
    }),
}))

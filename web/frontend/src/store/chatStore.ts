import { create } from 'zustand'
import type { ChatAttachmentRef, ChatMessage, SessionInfo, ToolCallInfo, UploadMeta, WsChatMessage } from '../types/api'
import { fetchJSON } from '../lib/api'

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
  pendingToolCalls: Record<string, ToolCallInfo>

  setSessionId: (id: string) => void
  setInputText: (t: string) => void
  setUseTools: (v: boolean) => void
  setPendingAttachments: (attachments: UploadMeta[]) => void
  addPendingAttachments: (attachments: UploadMeta[]) => void
  removePendingAttachment: (id: string) => void
  clearPendingAttachments: () => void
  fetchAvailableSessions: () => Promise<void>
  initChat: () => Promise<void>
  loadSession: () => Promise<void>
  newSession: () => void
  sendMessage: (
    sendChat: (sessionId: string, message: string, useTools: boolean, attachmentIds?: string[]) => void,
  ) => void
  abortChat: (abortChat: (sessionId: string) => void) => void
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

export const useChatStore = create<ChatState>((set, get) => ({
  sessionId: '',
  availableSessions: [],
  sessionsLoading: false,
  messages: [],
  inputText: '',
  pendingAttachments: [],
  streamBuffer: '',
  streaming: false,
  useTools: false,
  pendingToolCalls: {},

  setSessionId: (sessionId) => {
    set({ sessionId, pendingAttachments: [] })
    get().loadSession()
  },

  setInputText: (inputText) => set({ inputText }),
  setUseTools: (useTools) => set({ useTools }),
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
      set({ messages: [], pendingAttachments: [] })
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
      set({ messages, streamBuffer: '', streaming: false, pendingToolCalls: {}, pendingAttachments: [] })
    } catch {
      set({ messages: [], pendingAttachments: [] })
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
    }))
  },

  sendMessage: (sendChat) => {
    const { inputText, streaming, sessionId, useTools, pendingAttachments } = get()
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
    }))
    sendChat(sessionId, text, useTools, attachmentIds.length ? attachmentIds : undefined)
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
      }))
    } else {
      set({ streaming: false })
    }
  },

  handleChatMessage: (msg) => {
    const type = msg.type

    if (type === 'chat:chunk') {
      set((s) => ({ streamBuffer: s.streamBuffer + (msg.delta || '') }))
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
        const toolCalls = Object.values(s.pendingToolCalls)
        return {
          messages: [
            ...s.messages,
            {
              role: 'assistant' as const,
              content: s.streamBuffer || '(empty response)',
              tool_calls: toolCalls,
            },
          ],
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
    }),
}))

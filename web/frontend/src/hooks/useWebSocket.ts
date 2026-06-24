import { useEffect, useRef, useCallback } from 'react'
import { useAppStore } from '../store/appStore'
import type { WsChatMessage } from '../types/api'

type ChatHandler = (msg: WsChatMessage) => void

class WebSocketManager {
  private ws: WebSocket | null = null
  private reconnectDelay = 1000
  private maxReconnectDelay = 30000
  private handlers: Record<string, Array<(data: unknown, ts?: string, evtType?: string) => void>> = {}
  private chatHandlers: Record<string, ChatHandler[]> = {}
  private connected = false
  private onConnectionChange?: (connected: boolean) => void

  constructor(onConnectionChange?: (connected: boolean) => void) {
    this.onConnectionChange = onConnectionChange
  }

  get url() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    return `${proto}//${location.host}/ws`
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return
    }

    this.ws = new WebSocket(this.url)

    this.ws.onopen = () => {
      this.connected = true
      this.reconnectDelay = 1000
      this.onConnectionChange?.(true)
    }

    this.ws.onclose = () => {
      this.connected = false
      this.onConnectionChange?.(false)
      setTimeout(() => this.connect(), this.reconnectDelay)
      this.reconnectDelay = Math.min(this.reconnectDelay * 2, this.maxReconnectDelay)
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }

    this.ws.onmessage = (e) => {
      let msg: WsChatMessage & { type: string; event_type?: string; data?: unknown; timestamp?: string }
      try {
        msg = JSON.parse(e.data)
      } catch {
        return
      }

      if (msg.type === 'event') {
        const evtType = msg.event_type || 'unknown'
        ;(this.handlers[evtType] || []).forEach((fn) => fn(msg.data, msg.timestamp))
        ;(this.handlers['*'] || []).forEach((fn) => fn(msg.data, msg.timestamp, evtType))
      } else if (msg.type?.startsWith('chat:')) {
        const sid = msg.session_id || 'default'
        ;(this.chatHandlers[sid] || []).forEach((fn) => fn(msg))
      }
    }
  }

  on(eventType: string, fn: (data: unknown, ts?: string, evtType?: string) => void) {
    if (!this.handlers[eventType]) this.handlers[eventType] = []
    this.handlers[eventType].push(fn)
  }

  off(eventType: string, fn: (data: unknown, ts?: string, evtType?: string) => void) {
    if (!this.handlers[eventType]) return
    this.handlers[eventType] = this.handlers[eventType].filter((h) => h !== fn)
  }

  onChat(sessionId: string, fn: ChatHandler) {
    if (!this.chatHandlers[sessionId]) this.chatHandlers[sessionId] = []
    this.chatHandlers[sessionId].push(fn)
  }

  offChat(sessionId: string, fn: ChatHandler) {
    if (!this.chatHandlers[sessionId]) return
    this.chatHandlers[sessionId] = this.chatHandlers[sessionId].filter((h) => h !== fn)
  }

  send(msg: object) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg))
    }
  }

  ping() {
    this.send({ type: 'ping' })
  }

  sendChat(sessionId: string, message: string, useTools = false, attachmentIds?: string[]) {
    this.send({
      type: 'chat:send',
      session_id: sessionId,
      message,
      use_tools: useTools,
      attachment_ids: attachmentIds || [],
    })
  }

  abortChat(sessionId: string) {
    this.send({ type: 'chat:abort', session_id: sessionId })
  }

  isConnected() {
    return this.connected
  }
}

let manager: WebSocketManager | null = null

function getManager(onConnectionChange?: (connected: boolean) => void) {
  if (!manager) {
    manager = new WebSocketManager(onConnectionChange)
  }
  return manager
}

export function useWebSocket() {
  const setConnected = useAppStore((s) => s.setConnected)
  const addEvent = useAppStore((s) => s.addEvent)
  const fetchAgents = useAppStore((s) => s.fetchAgents)
  const fetchOverview = useAppStore((s) => s.fetchOverview)
  const handleOrchestratorWsEvent = useAppStore((s) => s.handleOrchestratorWsEvent)
  const wsRef = useRef<WebSocketManager | null>(null)

  useEffect(() => {
    const ws = getManager(setConnected)
    wsRef.current = ws
    ws.connect()

    const onAll = (data: unknown, ts?: string, evtType?: string) => {
      addEvent(evtType || 'unknown', data, ts)
    }
    ws.on('*', onAll)

    const onAgentSpawned = () => {
      fetchAgents()
      fetchOverview()
    }
    const onAgentStopped = () => {
      fetchAgents()
      fetchOverview()
    }
    const onOrchEvent = (data: unknown, _ts?: string, evtType?: string) => {
      if (evtType) handleOrchestratorWsEvent(evtType, data)
    }

    ws.on('agent:spawned', onAgentSpawned)
    ws.on('agent:stopped', onAgentStopped)
    for (const evt of [
      'orchestrator:started',
      'orchestrator:stage_start',
      'orchestrator:log',
      'orchestrator:done',
      'orchestrator:failed',
    ]) {
      ws.on(evt, onOrchEvent)
    }

    const pingInterval = setInterval(() => {
      if (ws.isConnected()) ws.ping()
    }, 30000)

    return () => {
      ws.off('*', onAll)
      ws.off('agent:spawned', onAgentSpawned)
      ws.off('agent:stopped', onAgentStopped)
      for (const evt of [
        'orchestrator:started',
        'orchestrator:stage_start',
        'orchestrator:log',
        'orchestrator:done',
        'orchestrator:failed',
      ]) {
        ws.off(evt, onOrchEvent)
      }
      clearInterval(pingInterval)
    }
  }, [setConnected, addEvent, fetchAgents, fetchOverview, handleOrchestratorWsEvent])

  const sendChat = useCallback(
    (sessionId: string, message: string, useTools: boolean, attachmentIds?: string[]) => {
      wsRef.current?.sendChat(sessionId, message, useTools, attachmentIds)
    },
    [],
  )

  const abortChat = useCallback((sessionId: string) => {
    wsRef.current?.abortChat(sessionId)
  }, [])

  const onChat = useCallback((sessionId: string, handler: ChatHandler) => {
    const ws = wsRef.current || getManager(setConnected)
    ws.onChat(sessionId, handler)
    return () => ws.offChat(sessionId, handler)
  }, [setConnected])

  return { sendChat, abortChat, onChat }
}

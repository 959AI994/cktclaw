export function timeAgo(ts?: string): string {
  const d = ts ? new Date(ts) : new Date()
  if (isNaN(d.getTime())) return ''
  const sec = Math.floor((Date.now() - d.getTime()) / 1000)
  if (sec < 5) return 'just now'
  if (sec < 60) return `${sec}s ago`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min}m ago`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr}h ago`
  return `${Math.floor(hr / 24)}d ago`
}

export function timeFormat(ts?: string): string {
  const d = ts ? new Date(ts) : new Date()
  if (isNaN(d.getTime())) return ''
  return d.toLocaleTimeString()
}

export function safeStringify(obj: unknown, space?: number): string {
  try {
    return JSON.stringify(obj, null, space)
  } catch {
    return '{}'
  }
}

export function agentId(a: { agent_id?: string; id?: string }): string {
  return a.agent_id || a.id || '?'
}

export function sessionId(s: { session_id?: string; id?: string }): string {
  return s.session_id || s.id || '?'
}

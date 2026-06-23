import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { useChatStore } from '../../store/chatStore'
import { safeStringify } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'

type MemoryTab = 'semantic' | 'session'

export function MemoryPanel() {
  const [tab, setTab] = useState<MemoryTab>('semantic')
  const chatSessionId = useChatStore((s) => s.sessionId)

  const memQuery = useAppStore((s) => s.memQuery)
  const memResults = useAppStore((s) => s.memResults)
  const memoryEntries = useAppStore((s) => s.memoryEntries)
  const memoryNote = useAppStore((s) => s.memoryNote)
  const memorySources = useAppStore((s) => s.memorySources)
  const sessionMemoryEntries = useAppStore((s) => s.sessionMemoryEntries)
  const setMemQuery = useAppStore((s) => s.setMemQuery)
  const searchMemory = useAppStore((s) => s.searchMemory)
  const fetchMemory = useAppStore((s) => s.fetchMemory)
  const fetchSessionMemory = useAppStore((s) => s.fetchSessionMemory)

  useEffect(() => {
    if (tab === 'semantic') fetchMemory()
    else if (chatSessionId) fetchSessionMemory(chatSessionId)
  }, [tab, chatSessionId, fetchMemory, fetchSessionMemory])

  const entryText = (e: unknown) => (typeof e === 'string' ? e : (e as { text?: string }).text || safeStringify(e))

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Memory</h2>

      <div className="flex gap-1">
        {(['semantic', 'session'] as MemoryTab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-md text-sm border cursor-pointer ${
              tab === t
                ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border-[var(--color-accent)]'
                : 'border-[var(--color-border)] text-[var(--color-text-secondary)]'
            }`}
          >
            {t === 'semantic' ? 'Semantic Memory' : 'Session Memory'}
          </button>
        ))}
      </div>

      {tab === 'semantic' && (
        <>
          {(memorySources.vector != null || memorySources.session != null) && (
            <div className="flex gap-2 text-xs">
              <Badge variant="muted">vector: {memorySources.vector ?? 0}</Badge>
              <Badge variant="muted">session DB: {memorySources.session ?? 0}</Badge>
            </div>
          )}

          <div className="flex gap-2 flex-wrap">
            <input
              type="text"
              className="field-input max-w-md flex-1"
              placeholder="Search semantic memories…"
              value={memQuery}
              onChange={(e) => setMemQuery(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && searchMemory()}
            />
            <Button variant="primary" onClick={searchMemory}>
              Search
            </Button>
            <Button size="sm" onClick={fetchMemory}>
              ↻ Refresh
            </Button>
          </div>

          <Card header="Search Results">
            <div className="p-3 space-y-2">
              {!memResults.length ? (
                <div className="text-sm text-[var(--color-text-dim)]">No results yet</div>
              ) : (
                memResults.map((r, i) => (
                  <div
                    key={i}
                    className="flex items-center justify-between px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm"
                  >
                    <span className="truncate flex-1">{r.text || safeStringify(r)}</span>
                    {r.score != null && (
                      <Badge variant="success" className="ml-2">
                        {Math.round(r.score * 100)}%
                      </Badge>
                    )}
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card header="Vector Store Entries">
            <div className="p-3 space-y-2">
              {memoryNote && !memoryEntries.length ? (
                <EmptyState variant="empty" title="Vector store unavailable" description={memoryNote} onRefresh={fetchMemory} />
              ) : !memoryEntries.length ? (
                <EmptyState
                  variant="empty"
                  title="No vector entries"
                  description="Semantic memory uses the vector store. Session memories are in the Session Memory tab."
                  onRefresh={fetchMemory}
                />
              ) : (
                memoryEntries.slice(0, 20).map((e, i) => (
                  <div key={i} className="px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm truncate">
                    {entryText(e)}
                  </div>
                ))
              )}
            </div>
          </Card>
        </>
      )}

      {tab === 'session' && (
        <>
          <p className="text-xs text-[var(--color-text-dim)]">
            Session: <code className="px-1 rounded bg-[var(--color-bg-overlay)]">{chatSessionId || 'none'}</code>
            {!chatSessionId && ' — open Chat tab and select a session first'}
          </p>
          <Button
            size="sm"
            onClick={() => chatSessionId && fetchSessionMemory(chatSessionId)}
            disabled={!chatSessionId}
          >
            ↻ Refresh
          </Button>

          <Card header="CktMem Session Memories">
            <div className="p-3 space-y-2">
              {!chatSessionId ? (
                <EmptyState variant="empty" title="No session selected" description="Select a session in the Chat tab." />
              ) : !sessionMemoryEntries.length ? (
                <EmptyState
                  variant="empty"
                  title="No session memories"
                  description="Memory entries saved during CLI or agent runs appear here (SQLite session_memories table)."
                  onRefresh={() => fetchSessionMemory(chatSessionId)}
                />
              ) : (
                sessionMemoryEntries.map((e, i) => (
                  <div key={i} className="px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm">
                    {e.topic && <div className="font-medium text-[var(--color-accent)] mb-1">{e.topic}</div>}
                    {e.summary && <div className="text-[var(--color-text-secondary)] mb-1">{e.summary}</div>}
                    <div>{e.content || safeStringify(e)}</div>
                  </div>
                ))
              )}
            </div>
          </Card>
        </>
      )}
    </div>
  )
}

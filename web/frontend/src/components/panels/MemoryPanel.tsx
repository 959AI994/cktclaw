import { useEffect, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { useChatStore } from '../../store/chatStore'
import { safeStringify } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'

type MemoryTab = 'semantic' | 'session'

function sessionLabel(id: string, title?: string) {
  if (title) return `${title} (${id.slice(0, 8)}…)`
  return id.length > 12 ? `${id.slice(0, 12)}…` : id
}

export function MemoryPanel() {
  const [tab, setTab] = useState<MemoryTab>('semantic')
  const chatSessionId = useChatStore((s) => s.sessionId)

  const sessions = useAppStore((s) => s.sessions)
  const memQuery = useAppStore((s) => s.memQuery)
  const memResults = useAppStore((s) => s.memResults)
  const memoryEntries = useAppStore((s) => s.memoryEntries)
  const memoryNote = useAppStore((s) => s.memoryNote)
  const embeddingsAvailable = useAppStore((s) => s.embeddingsAvailable)
  const embeddingBackend = useAppStore((s) => s.embeddingBackend)
  const embeddingModel = useAppStore((s) => s.embeddingModel)
  const memorySources = useAppStore((s) => s.memorySources)
  const sessionMemoryEntries = useAppStore((s) => s.sessionMemoryEntries)
  const allSessionMemoryEntries = useAppStore((s) => s.allSessionMemoryEntries)
  const setMemQuery = useAppStore((s) => s.setMemQuery)
  const searchMemory = useAppStore((s) => s.searchMemory)
  const fetchMemory = useAppStore((s) => s.fetchMemory)
  const fetchSessions = useAppStore((s) => s.fetchSessions)
  const fetchSessionMemory = useAppStore((s) => s.fetchSessionMemory)
  const fetchAllSessionMemories = useAppStore((s) => s.fetchAllSessionMemories)
  const saveSessionMemory = useAppStore((s) => s.saveSessionMemory)

  const [selectedSessionId, setSelectedSessionId] = useState('')
  const [showAllSessions, setShowAllSessions] = useState(false)
  const [saveForm, setSaveForm] = useState({ topic: '', summary: '', content: '' })

  useEffect(() => {
    if (tab === 'semantic') fetchMemory()
    else {
      fetchSessions()
      fetchAllSessionMemories()
    }
  }, [tab, fetchMemory, fetchSessions, fetchAllSessionMemories])

  useEffect(() => {
    if (chatSessionId && !selectedSessionId) {
      setSelectedSessionId(chatSessionId)
    }
  }, [chatSessionId, selectedSessionId])

  useEffect(() => {
    if (tab === 'session' && selectedSessionId) {
      fetchSessionMemory(selectedSessionId)
    }
  }, [tab, selectedSessionId, fetchSessionMemory])

  const entryText = (e: unknown) => (typeof e === 'string' ? e : (e as { text?: string }).text || safeStringify(e))

  const handleSaveSessionMemory = async () => {
    if (!selectedSessionId) return
    const { topic, summary, content } = saveForm
    if (!topic.trim() || !summary.trim() || !content.trim()) return
    await saveSessionMemory({
      session_id: selectedSessionId,
      topic: topic.trim(),
      summary: summary.trim(),
      content: content.trim(),
    })
    setSaveForm({ topic: '', summary: '', content: '' })
  }

  const displayedSessionEntries = showAllSessions ? allSessionMemoryEntries : sessionMemoryEntries

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
          <div className="flex gap-2 flex-wrap text-xs items-center">
            {embeddingsAvailable === false && (
              <Badge variant="danger">embeddings unavailable</Badge>
            )}
            {embeddingsAvailable === true && <Badge variant="success">embeddings ready</Badge>}
            {embeddingBackend && <Badge variant="muted">backend: {embeddingBackend}</Badge>}
            {embeddingModel && <Badge variant="muted">model: {embeddingModel}</Badge>}
            {(memorySources.vector != null || memorySources.session != null) && (
              <>
                <Badge variant="muted">vector: {memorySources.vector ?? 0}</Badge>
                <Badge variant="muted">session DB: {memorySources.session ?? 0}</Badge>
              </>
            )}
          </div>

          {embeddingsAvailable === false && memoryNote && (
            <div className="text-sm text-[var(--color-text-secondary)] rounded-md border border-[var(--color-border)] p-3 bg-[var(--color-bg-overlay)]">
              <div className="font-medium mb-1">Semantic memory disabled</div>
              <div className="whitespace-pre-wrap">{memoryNote}</div>
              <div className="mt-2 text-xs text-[var(--color-text-dim)]">
                Local BGE is installed by setup.sh. For Jina cloud embeddings, add{' '}
                <code className="px-1 rounded bg-[var(--color-bg)]">JINA_API_KEY</code> to .env
              </div>
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
              disabled={embeddingsAvailable === false}
            />
            <Button variant="primary" onClick={searchMemory} disabled={embeddingsAvailable === false}>
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
                    className="flex flex-col gap-1 px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate flex-1">{r.text || safeStringify(r)}</span>
                      {r.score != null && (
                        <Badge variant="success" className="ml-2 shrink-0">
                          {Math.round(r.score * 100)}%
                        </Badge>
                      )}
                    </div>
                    {r.metadata && (
                      <div className="text-xs text-[var(--color-text-dim)] truncate">
                        {safeStringify(r.metadata)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </Card>

          <Card header="Vector Store Entries">
            <div className="p-3 space-y-2">
              {embeddingsAvailable === false ? (
                <EmptyState variant="empty" title="Embeddings not installed" description={memoryNote || undefined} onRefresh={fetchMemory} />
              ) : !memoryEntries.length ? (
                <EmptyState
                  variant="empty"
                  title="No vector entries"
                  description="Chat replies are indexed automatically after you install sentence-transformers. Session memories are in the Session Memory tab."
                  onRefresh={fetchMemory}
                />
              ) : (
                memoryEntries.slice(0, 20).map((e, i) => (
                  <div key={e.id || i} className="px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm">
                    <div className="truncate">{entryText(e)}</div>
                    {e.metadata && (
                      <div className="text-xs text-[var(--color-text-dim)] mt-1 truncate">
                        {safeStringify(e.metadata)}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>
          </Card>
        </>
      )}

      {tab === 'session' && (
        <>
          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex-1 min-w-[200px]">
              <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Session</label>
              <select
                className="field-input w-full"
                value={selectedSessionId}
                onChange={(e) => setSelectedSessionId(e.target.value)}
              >
                <option value="">Select a session…</option>
                {sessions.map((s) => {
                  const id = s.session_id || s.id || ''
                  if (!id) return null
                  return (
                    <option key={id} value={id}>
                      {sessionLabel(id, s.session_title)}
                    </option>
                  )
                })}
                {chatSessionId && !sessions.some((s) => (s.session_id || s.id) === chatSessionId) && (
                  <option value={chatSessionId}>{sessionLabel(chatSessionId)}</option>
                )}
              </select>
            </div>
            <Button size="sm" onClick={() => selectedSessionId && fetchSessionMemory(selectedSessionId)} disabled={!selectedSessionId}>
              ↻ Refresh
            </Button>
            <Button
              size="sm"
              variant={showAllSessions ? 'primary' : undefined}
              onClick={() => setShowAllSessions((v) => !v)}
            >
              {showAllSessions ? 'Per-session view' : 'All sessions'}
            </Button>
          </div>

          {selectedSessionId && !showAllSessions && (
            <Card header="Save Session Memory">
              <div className="p-3 space-y-2">
                <input
                  className="field-input w-full"
                  placeholder="Topic (e.g. circuit_adder)"
                  value={saveForm.topic}
                  onChange={(e) => setSaveForm((f) => ({ ...f, topic: e.target.value }))}
                />
                <input
                  className="field-input w-full"
                  placeholder="One-line summary"
                  value={saveForm.summary}
                  onChange={(e) => setSaveForm((f) => ({ ...f, summary: e.target.value }))}
                />
                <textarea
                  className="field-input w-full min-h-[80px]"
                  placeholder="Full content"
                  value={saveForm.content}
                  onChange={(e) => setSaveForm((f) => ({ ...f, content: e.target.value }))}
                />
                <Button variant="primary" size="sm" onClick={handleSaveSessionMemory}>
                  Save to session
                </Button>
              </div>
            </Card>
          )}

          <Card header={showAllSessions ? 'All Session Memories' : 'CktMem Session Memories'}>
            <div className="p-3 space-y-2">
              {!showAllSessions && !selectedSessionId ? (
                <EmptyState variant="empty" title="No session selected" description="Pick a session from the dropdown or open Chat." />
              ) : !displayedSessionEntries.length ? (
                <EmptyState
                  variant="empty"
                  title="No session memories"
                  description="Save manually above, or enable Tools in Chat so the model can call save_session_memory."
                  onRefresh={() => {
                    if (showAllSessions) fetchAllSessionMemories()
                    else if (selectedSessionId) fetchSessionMemory(selectedSessionId)
                  }}
                />
              ) : (
                displayedSessionEntries.map((e, i) => (
                  <div key={`${e.session_id || selectedSessionId}-${e.topic || i}`} className="px-3 py-2 rounded-md bg-[var(--color-bg-overlay)] text-sm">
                    {showAllSessions && e.session_id && (
                      <div className="text-xs text-[var(--color-text-dim)] mb-1 font-mono">{e.session_id}</div>
                    )}
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

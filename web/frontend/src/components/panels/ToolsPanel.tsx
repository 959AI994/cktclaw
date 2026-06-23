import { useMemo, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import type { ToolInfo } from '../../types/api'
import { safeStringify } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import { SearchInput } from '../ui/SearchInput'

export function ToolsPanel() {
  const tools = useAppStore((s) => s.tools)
  const toolsLoading = useAppStore((s) => s.toolsLoading)
  const toolsError = useAppStore((s) => s.toolsError)
  const fetchTools = useAppStore((s) => s.fetchTools)

  const [search, setSearch] = useState('')
  const [category, setCategory] = useState('all')
  const [schemaTool, setSchemaTool] = useState<ToolInfo | null>(null)

  const categories = useMemo(() => {
    const cats = new Set(tools.map((t) => t.category || 'general'))
    return ['all', ...Array.from(cats).sort()]
  }, [tools])

  const categoryCounts = useMemo(() => {
    const counts: Record<string, number> = { all: tools.length }
    for (const t of tools) {
      const cat = t.category || 'general'
      counts[cat] = (counts[cat] || 0) + 1
    }
    return counts
  }, [tools])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return tools.filter((t) => {
      if (category !== 'all' && (t.category || 'general') !== category) return false
      if (!q) return true
      return (
        t.name.toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
      )
    })
  }, [tools, search, category])

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Tools</h2>

      {!toolsLoading && tools.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <Badge variant="accent">Total: {tools.length}</Badge>
          {Object.entries(categoryCounts)
            .filter(([k]) => k !== 'all')
            .map(([cat, n]) => (
              <Badge key={cat} variant="muted">
                {cat}: {n}
              </Badge>
            ))}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search tools…" />
        <Button size="sm" onClick={fetchTools} disabled={toolsLoading}>
          ↻ Refresh
        </Button>
      </div>

      <div className="flex flex-wrap gap-1">
        {categories.map((cat) => (
          <button
            key={cat}
            type="button"
            onClick={() => setCategory(cat)}
            className={`px-2.5 py-1 rounded-md text-xs border cursor-pointer transition-colors ${
              category === cat
                ? 'bg-[var(--color-accent-subtle)] text-[var(--color-accent)] border-[var(--color-accent)]'
                : 'bg-transparent text-[var(--color-text-secondary)] border-[var(--color-border)] hover:bg-[var(--color-bg-overlay)]'
            }`}
          >
            {cat === 'all' ? 'All' : cat}
            {categoryCounts[cat] != null ? ` (${categoryCounts[cat]})` : ''}
          </button>
        ))}
      </div>

      {toolsLoading ? (
        <EmptyState variant="loading" title="Loading tools…" />
      ) : toolsError ? (
        <EmptyState
          variant="error"
          title="Failed to load tools"
          description={toolsError}
          onRefresh={fetchTools}
        />
      ) : filtered.length === 0 ? (
        <EmptyState
          variant="empty"
          title={tools.length === 0 ? 'No tools registered' : 'No matching tools'}
          description={
            tools.length === 0
              ? 'Built-in EDA and system tools appear here after runtime bootstrap.'
              : 'Try a different search or category filter.'
          }
          onRefresh={fetchTools}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((t) => (
            <Card key={t.name} className="p-3.5 flex flex-col">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                <Badge variant="accent">{t.category || 'general'}</Badge>
                <strong className="font-[family-name:var(--font-mono)] text-sm">{t.name}</strong>
                {t.read_only && <Badge variant="success">ro</Badge>}
                {t.source && <Badge variant="muted">{t.source}</Badge>}
              </div>
              <div className="text-sm text-[var(--color-text-secondary)] flex-1 line-clamp-3">
                {t.description || 'No description'}
              </div>
              {(t.requires || []).length > 0 && (
                <div className="text-[0.72rem] text-[var(--color-text-dim)] mt-2">
                  requires: {(t.requires || []).join(', ')}
                </div>
              )}
              <Button size="sm" className="mt-3 self-start" onClick={() => setSchemaTool(t)}>
                View Schema
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={!!schemaTool}
        onClose={() => setSchemaTool(null)}
        title={schemaTool ? `🔧 ${schemaTool.name}` : ''}
        actions={<Button onClick={() => setSchemaTool(null)}>Close</Button>}
      >
        {schemaTool && (
          <div className="space-y-3 text-sm">
            <p className="text-[var(--color-text-secondary)]">{schemaTool.description}</p>
            <div>
              <div className="text-xs text-[var(--color-text-dim)] mb-1">Parameters (JSON Schema)</div>
              <pre className="p-3 rounded-md overflow-x-auto text-xs bg-[var(--color-bg-root)] border border-[var(--color-border)] font-[family-name:var(--font-mono)]">
                {safeStringify(schemaTool.parameters, 2)}
              </pre>
            </div>
          </div>
        )}
      </Modal>
    </div>
  )
}

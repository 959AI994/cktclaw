import { useMemo, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { fetchJSON } from '../../lib/api'
import type { SkillDetail, SkillInfo } from '../../types/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'
import { SearchInput } from '../ui/SearchInput'

export function SkillsPanel() {
  const skills = useAppStore((s) => s.skills)
  const skillStats = useAppStore((s) => s.skillStats)
  const skillsLoading = useAppStore((s) => s.skillsLoading)
  const skillsError = useAppStore((s) => s.skillsError)
  const fetchSkills = useAppStore((s) => s.fetchSkills)
  const toast = useAppStore((s) => s.toast)

  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [showHidden, setShowHidden] = useState(false)
  const [detail, setDetail] = useState<SkillDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  const total = skillStats.total_skills ?? skillStats.total ?? skills.length

  const types = useMemo(() => {
    const fromStats = Object.keys(skillStats.by_type || {})
    const fromSkills = skills.map((s) => s.skill_type || 'unknown')
    return ['all', ...Array.from(new Set([...fromStats, ...fromSkills])).filter(Boolean).sort()]
  }, [skills, skillStats])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return skills.filter((s) => {
      if (!showHidden && (s.is_hidden || s.user_invocable === false)) return false
      if (typeFilter !== 'all' && (s.skill_type || 'unknown') !== typeFilter) return false
      if (!q) return true
      const hay = [s.name, s.display_name, s.description, ...(s.aliases || [])].join(' ').toLowerCase()
      return hay.includes(q)
    })
  }, [skills, search, typeFilter, showHidden])

  const openDetail = async (skill: SkillInfo) => {
    setDetailLoading(true)
    setDetail({ ...skill })
    try {
      const d = await fetchJSON<SkillDetail>(`/api/skills/${encodeURIComponent(skill.name)}`)
      setDetail(d)
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Failed to load skill detail')
    } finally {
      setDetailLoading(false)
    }
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Skills</h2>

      {!skillsLoading && total > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
          <StatChip label="Total" value={total} accent />
          {Object.entries(skillStats.by_type || {}).map(([type, n]) => (
            <StatChip key={type} label={type} value={n} />
          ))}
        </div>
      )}

      {Object.keys(skillStats.by_source || {}).length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(skillStats.by_source || {}).map(([src, n]) => (
            <Badge key={src} variant="muted">
              {src}: {n}
            </Badge>
          ))}
          {(skillStats.total_aliases ?? 0) > 0 && (
            <Badge variant="cyan">aliases: {skillStats.total_aliases}</Badge>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <SearchInput value={search} onChange={setSearch} placeholder="Search skills…" />
        <select
          className="field-input max-w-[140px] text-sm"
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
        >
          {types.map((t) => (
            <option key={t} value={t}>
              {t === 'all' ? 'All types' : t}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-[var(--color-text-secondary)] cursor-pointer">
          <input type="checkbox" checked={showHidden} onChange={(e) => setShowHidden(e.target.checked)} />
          Show hidden
        </label>
        <Button size="sm" onClick={fetchSkills} disabled={skillsLoading}>
          ↻ Refresh
        </Button>
      </div>

      {skillsLoading ? (
        <EmptyState variant="loading" title="Loading skills…" />
      ) : skillsError ? (
        <EmptyState variant="error" title="Failed to load skills" description={skillsError} onRefresh={fetchSkills} />
      ) : filtered.length === 0 ? (
        <EmptyState
          variant="empty"
          title={skills.length === 0 ? 'No skills loaded' : 'No matching skills'}
          description={
            skills.length === 0
              ? 'Bundled and plugin skills register at startup.'
              : 'Adjust filters or search query.'
          }
          onRefresh={fetchSkills}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {filtered.map((s) => (
            <Card key={s.name} className="p-3.5 flex flex-col">
              <div className="flex items-center gap-2 mb-2 flex-wrap">
                {s.skill_type && <Badge variant="purple">{s.skill_type}</Badge>}
                <strong className="font-[family-name:var(--font-mono)] text-sm">{s.display_name || s.name}</strong>
                {!s.user_invocable && <Badge variant="muted">hidden</Badge>}
              </div>
              <div className="text-sm text-[var(--color-text-secondary)] flex-1 line-clamp-3">
                {s.description || 'No description'}
              </div>
              <div className="flex gap-1 mt-2 flex-wrap">
                {(s.aliases || []).slice(0, 3).map((a) => (
                  <Badge key={a} variant="cyan">
                    {a}
                  </Badge>
                ))}
                {s.loaded_from && <Badge variant="muted">{s.loaded_from}</Badge>}
              </div>
              <Button size="sm" className="mt-3 self-start" onClick={() => openDetail(s)}>
                Details
              </Button>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={!!detail}
        onClose={() => setDetail(null)}
        title={detail ? `⬢ ${detail.display_name || detail.name}` : ''}
        actions={<Button onClick={() => setDetail(null)}>Close</Button>}
      >
        {detail && (
          <div className="space-y-3 text-sm max-h-[60vh] overflow-y-auto">
            {detailLoading && <p className="text-[var(--color-text-dim)]">Loading…</p>}
            <div className="flex flex-wrap gap-1">
              {detail.skill_type && <Badge variant="purple">{detail.skill_type}</Badge>}
              {detail.loaded_from && <Badge variant="muted">{detail.loaded_from}</Badge>}
              {detail.version && <Badge variant="accent">v{detail.version}</Badge>}
            </div>
            <p className="text-[var(--color-text-secondary)]">{detail.description}</p>
            {detail.when_to_use && (
              <div>
                <div className="text-xs font-medium text-[var(--color-text-dim)] mb-1">When to use</div>
                <p className="text-[var(--color-text-secondary)]">{detail.when_to_use}</p>
              </div>
            )}
            {detail.argument_hint && (
              <div>
                <div className="text-xs font-medium text-[var(--color-text-dim)] mb-1">Argument hint</div>
                <code className="text-xs">{detail.argument_hint}</code>
              </div>
            )}
            {(detail.allowed_tools || []).length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--color-text-dim)] mb-1">Allowed tools</div>
                <div className="flex flex-wrap gap-1">
                  {detail.allowed_tools!.map((t) => (
                    <Badge key={t} variant="accent">
                      {t}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
            {(detail.aliases || []).length > 0 && (
              <div>
                <div className="text-xs font-medium text-[var(--color-text-dim)] mb-1">Aliases</div>
                <div className="flex flex-wrap gap-1">
                  {detail.aliases!.map((a) => (
                    <Badge key={a} variant="cyan">
                      {a}
                    </Badge>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </Modal>
    </div>
  )
}

function StatChip({ label, value, accent }: { label: string; value: number; accent?: boolean }) {
  return (
    <div
      className={`rounded-lg border px-3 py-2 text-center ${accent ? 'border-[var(--color-accent)] bg-[var(--color-accent-subtle)]' : 'border-[var(--color-border)] bg-[var(--color-bg-surface)]'}`}
    >
      <div className={`text-lg font-bold font-[family-name:var(--font-mono)] ${accent ? 'text-[var(--color-accent)]' : ''}`}>
        {value}
      </div>
      <div className="text-[0.72rem] text-[var(--color-text-secondary)]">{label}</div>
    </div>
  )
}

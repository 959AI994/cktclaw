import { useAppStore } from '../../store/appStore'
import { Badge } from '../ui/Badge'
import { Card } from '../ui/Card'
import { safeStringify, timeFormat } from '../../lib/utils'

export function OverviewPanel() {
  const status = useAppStore((s) => s.status)
  const providers = useAppStore((s) => s.providers)
  const events = useAppStore((s) => s.events)
  const skillStats = useAppStore((s) => s.skillStats)

  const toolNames = status.tools?.names || []
  const skillsCount = status.skills?.count ?? skillStats.total_skills ?? skillStats.total ?? 0

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Dashboard Overview</h2>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <MetricCard value={status.model?.current || '—'} label="Active Model" sub={status.model?.model} />
        <MetricCard value={String(status.tools?.count || 0)} label="Tools" />
        <MetricCard value={String(skillsCount)} label="Skills" />
        <MetricCard value={String((status.agents || []).length)} label="Active Agents" />
      </div>

      {(toolNames.length > 0 || skillsCount > 0) && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
          {toolNames.length > 0 && (
            <Card header="Registered Tools">
              <div className="p-3 flex flex-wrap gap-1">
                {toolNames.map((n) => (
                  <Badge key={n} variant="accent">
                    {n}
                  </Badge>
                ))}
              </div>
            </Card>
          )}
          {Object.keys(skillStats.by_type || {}).length > 0 && (
            <Card header="Skills by Type">
              <div className="p-3 flex flex-wrap gap-2">
                {Object.entries(skillStats.by_type || {}).map(([type, n]) => (
                  <Badge key={type} variant="purple">
                    {type}: {n}
                  </Badge>
                ))}
              </div>
            </Card>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <Card header="System Health">
          <div className="p-4 space-y-2 text-sm">
            <Row label="Uptime" value={status.uptime_seconds ? `${Math.floor(status.uptime_seconds)}s` : '—'} mono />
            <Row
              label="API Cost"
              value={`$${(status.harness?.total_cost_usd || 0).toFixed(4)}`}
              mono
            />
            <Row label="Session" value={status.harness?.session_id || '—'} mono small />
            {status.tasks?.total_tasks != null && (
              <Row label="Tasks" value={String(status.tasks.total_tasks)} mono />
            )}
          </div>
        </Card>

        <Card header="Providers">
          <div className="p-4 space-y-2">
            {Object.entries(providers).length === 0 ? (
              <div className="text-sm text-[var(--color-text-dim)]">No providers configured</div>
            ) : (
              Object.entries(providers).map(([name, p]) => (
                <div key={name} className="flex items-center justify-between text-sm">
                  <span>{p.label}</span>
                  <span className="flex gap-1">
                    <Badge variant={p.is_available ? 'success' : 'muted'}>
                      {p.is_available ? 'ready' : 'no key'}
                    </Badge>
                    {p.is_current && <Badge variant="accent">active</Badge>}
                  </span>
                </div>
              ))
            )}
          </div>
        </Card>
      </div>

      <Card header="Event Feed">
        <div className="max-h-[320px] overflow-y-auto p-2 font-[family-name:var(--font-mono)] text-xs">
          {events.length === 0 ? (
            <div className="text-[var(--color-text-dim)] p-2">Waiting for events…</div>
          ) : (
            events.map((evt, i) => (
              <EventRow key={i} event_type={evt.event_type} data={evt.data} timestamp={evt.timestamp} />
            ))
          )}
        </div>
      </Card>
    </div>
  )
}

function MetricCard({ value, label, sub }: { value: string; label: string; sub?: string }) {
  return (
    <Card className="p-4 text-center">
      <div className="text-xl font-bold font-[family-name:var(--font-mono)] text-[var(--color-accent)]">{value}</div>
      <div className="text-xs text-[var(--color-text-secondary)] mt-1">{label}</div>
      {sub && <div className="text-[0.72rem] text-[var(--color-text-dim)] mt-0.5">{sub}</div>}
    </Card>
  )
}

function Row({ label, value, mono, small }: { label: string; value: string; mono?: boolean; small?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-[var(--color-text-secondary)]">{label}</span>
      <span className={`${mono ? 'font-[family-name:var(--font-mono)]' : ''} ${small ? 'text-xs' : ''}`}>{value}</span>
    </div>
  )
}

function EventRow({ event_type, data, timestamp }: { event_type: string; data: unknown; timestamp?: string }) {
  const tagCls = event_type.startsWith('agent')
    ? 'text-[var(--color-warning)]'
    : event_type.startsWith('plugin')
      ? 'text-[var(--color-purple)]'
      : event_type.startsWith('model')
        ? 'text-[var(--color-accent)]'
        : event_type.startsWith('chat')
          ? 'text-[var(--color-cyan)]'
          : 'text-[var(--color-text-secondary)]'

  return (
    <div className="flex gap-2 py-1 border-b border-[var(--color-border-muted)] last:border-0">
      <span className="text-[var(--color-text-dim)] shrink-0">{timeFormat(timestamp)}</span>
      <span className={`shrink-0 ${tagCls}`}>{event_type}</span>
      <span className="text-[var(--color-text-secondary)] truncate">{safeStringify(data).slice(0, 300)}</span>
    </div>
  )
}

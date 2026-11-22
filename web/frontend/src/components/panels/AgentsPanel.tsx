import { useMemo, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { agentId } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { Modal } from '../ui/Modal'
import { AttachmentUploader } from '../upload/AttachmentUploader'
import { Table, TableRow, TableCell } from '../ui/Table'

export function AgentsPanel() {
  const agentsSubTab = useAppStore((s) => s.agentsSubTab)
  const setAgentsSubTab = useAppStore((s) => s.setAgentsSubTab)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-lg font-semibold">Agents</h2>
        <div className="flex rounded-lg border border-[var(--color-border)] overflow-hidden">
          <TabButton active={agentsSubTab === 'worker'} onClick={() => setAgentsSubTab('worker')}>
            Worker Agents
          </TabButton>
          <TabButton active={agentsSubTab === 'specialist'} onClick={() => setAgentsSubTab('specialist')}>
            Chip Specialists
          </TabButton>
        </div>
      </div>

      {agentsSubTab === 'worker' ? <WorkerAgentsTab /> : <SpecialistTab />}
    </div>
  )
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'bg-[var(--color-accent)] text-white'
          : 'bg-[var(--color-surface)] text-[var(--color-text-secondary)] hover:text-[var(--color-text)]'
      }`}
    >
      {children}
    </button>
  )
}

function WorkerAgentsTab() {
  const agents = useAppStore((s) => s.agents)
  const providers = useAppStore((s) => s.providers)
  const fetchAgents = useAppStore((s) => s.fetchAgents)
  const stopAgent = useAppStore((s) => s.stopAgent)
  const viewAgent = useAppStore((s) => s.viewAgent)
  const showSpawn = useAppStore((s) => s.showSpawn)
  const setShowSpawn = useAppStore((s) => s.setShowSpawn)
  const spawnForm = useAppStore((s) => s.spawnForm)
  const setSpawnForm = useAppStore((s) => s.setSpawnForm)
  const spawnAgent = useAppStore((s) => s.spawnAgent)
  const spawnAttachments = useAppStore((s) => s.spawnAttachments)
  const setSpawnAttachments = useAppStore((s) => s.setSpawnAttachments)
  const agentUploadSessionId = useAppStore((s) => s.agentUploadSessionId)

  const providerOptions = useMemo(
    () => Object.entries(providers).map(([key, p]) => ({ key, label: p.label || key })),
    [providers],
  )

  return (
    <>
      <div className="flex gap-2">
        <Button variant="primary" onClick={() => setShowSpawn(true)}>
          + Spawn Agent
        </Button>
        <Button size="sm" onClick={fetchAgents}>
          ↻ Refresh
        </Button>
      </div>

      <Table headers={['ID', 'Name', 'Status', 'Model', 'Turns', '']} colWidths={['', '', '', '', '', '120px']}>
        {!agents.length ? (
          <TableRow>
            <TableCell className="text-[var(--color-text-dim)]" colSpan={6}>
              No agents running. Spawn one to get started.
            </TableCell>
          </TableRow>
        ) : (
          agents.map((a) => {
            const id = agentId(a)
            const turns = a.budget ? `${a.budget.turns_used || 0}/${a.budget.max_turns || '?'}` : '—'
            return (
              <TableRow key={id}>
                <TableCell>
                  <code className="text-xs">{id}</code>
                </TableCell>
                <TableCell>{a.name || '?'}</TableCell>
                <TableCell>
                  <Badge variant={statusBadge(a.status)}>{a.status || '?'}</Badge>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-[var(--color-text-secondary)]">{a.model || '—'}</span>
                </TableCell>
                <TableCell>
                  <span className="font-[family-name:var(--font-mono)] text-xs">{turns}</span>
                </TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button size="sm" onClick={() => viewAgent(id)}>
                      Detail
                    </Button>
                    {a.status === 'running' && (
                      <Button size="sm" variant="danger" onClick={() => stopAgent(id)}>
                        Stop
                      </Button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            )
          })
        )}
      </Table>

      <Modal
        open={showSpawn}
        onClose={() => setShowSpawn(false)}
        title="◆ Spawn Agent"
        actions={
          <>
            <Button onClick={() => setShowSpawn(false)}>Cancel</Button>
            <Button variant="primary" onClick={spawnAgent}>
              Spawn
            </Button>
          </>
        }
      >
        <FormField label="Name">
          <input
            className="field-input"
            placeholder="my-agent"
            value={spawnForm.name}
            onChange={(e) => setSpawnForm({ name: e.target.value })}
          />
        </FormField>
        <FormField label="Task *">
          <textarea
            className="field-input"
            rows={3}
            placeholder="What should this agent do?"
            value={spawnForm.task}
            onChange={(e) => setSpawnForm({ task: e.target.value })}
          />
        </FormField>
        <FormField label="System Prompt">
          <textarea
            className="field-input"
            rows={2}
            placeholder="Optional"
            value={spawnForm.system_prompt}
            onChange={(e) => setSpawnForm({ system_prompt: e.target.value })}
          />
        </FormField>
        <FormField label="Model">
          {providerOptions.length ? (
            <select
              className="field-input"
              value={spawnForm.model}
              onChange={(e) => setSpawnForm({ model: e.target.value })}
            >
              <option value="">auto (deepseek)</option>
              {providerOptions.map((p) => (
                <option key={p.key} value={p.key}>
                  {p.label}
                </option>
              ))}
            </select>
          ) : (
            <input
              className="field-input"
              placeholder="auto"
              value={spawnForm.model}
              onChange={(e) => setSpawnForm({ model: e.target.value })}
            />
          )}
        </FormField>
        <FormField label="Attachments">
          <AttachmentUploader
            sessionId={agentUploadSessionId}
            attachments={spawnAttachments}
            onChange={setSpawnAttachments}
          />
        </FormField>
      </Modal>
    </>
  )
}

function SpecialistTab() {
  const skills = useAppStore((s) => s.skills)
  const orchestratorRuns = useAppStore((s) => s.orchestratorRuns)
  const orchestratorForm = useAppStore((s) => s.orchestratorForm)
  const setOrchestratorForm = useAppStore((s) => s.setOrchestratorForm)
  const runOrchestrator = useAppStore((s) => s.runOrchestrator)
  const abortOrchestrator = useAppStore((s) => s.abortOrchestrator)
  const fetchOrchestratorRuns = useAppStore((s) => s.fetchOrchestratorRuns)
  const orchestratorAttachments = useAppStore((s) => s.orchestratorAttachments)
  const setOrchestratorAttachments = useAppStore((s) => s.setOrchestratorAttachments)
  const orchestratorUploadSessionId = useAppStore((s) => s.orchestratorUploadSessionId)
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)

  const chipSkills = useMemo(
    () => skills.filter((s) => s.name.startsWith('chip-')).sort((a, b) => a.name.localeCompare(b.name)),
    [skills],
  )

  const selectedRun = orchestratorRuns.find((r) => r.run_id === selectedRunId) || orchestratorRuns[0]

  return (
    <>
      <p className="text-sm text-[var(--color-text-secondary)]">
        Run chip-design orchestrators (same as CLI <code>/chip-rtl</code>, etc.). Tasks may take several minutes.
      </p>

      <div className="grid gap-3 p-4 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)]">
        <FormField label="Specialist Skill *">
          <select
            className="field-input"
            value={orchestratorForm.skill}
            onChange={(e) => setOrchestratorForm({ skill: e.target.value })}
          >
            {chipSkills.length === 0 && <option value="">Loading chip skills…</option>}
            {chipSkills.map((s) => (
              <option key={s.name} value={s.name}>
                {s.display_name || s.name}
              </option>
            ))}
          </select>
        </FormField>
        <FormField label="Task *">
          <textarea
            className="field-input"
            rows={4}
            placeholder="Describe your design task in detail (≥80 chars recommended for best results)"
            value={orchestratorForm.task}
            onChange={(e) => setOrchestratorForm({ task: e.target.value })}
          />
        </FormField>
        <FormField label="Attachments">
          <AttachmentUploader
            sessionId={orchestratorUploadSessionId}
            attachments={orchestratorAttachments}
            onChange={setOrchestratorAttachments}
          />
        </FormField>
        <div className="flex gap-2">
          <Button variant="primary" onClick={runOrchestrator}>
            Run Orchestrator
          </Button>
          <Button size="sm" onClick={fetchOrchestratorRuns}>
            ↻ Refresh
          </Button>
        </div>
      </div>

      <Table headers={['Run ID', 'Skill', 'Status', 'Stage', '']} colWidths={['', '', '', '', '100px']}>
        {!orchestratorRuns.length ? (
          <TableRow>
            <TableCell className="text-[var(--color-text-dim)]" colSpan={5}>
              No orchestrator runs yet.
            </TableCell>
          </TableRow>
        ) : (
          orchestratorRuns.map((r) => {
            const stage =
              r.current_stage && r.stage_total
                ? `${r.current_stage} (${r.stage_index}/${r.stage_total})`
                : r.current_stage || '—'
            return (
              <TableRow key={r.run_id}>
                <TableCell>
                  <button
                    type="button"
                    className="text-xs font-mono text-[var(--color-accent)] hover:underline"
                    onClick={() => setSelectedRunId(r.run_id)}
                  >
                    {r.run_id}
                  </button>
                </TableCell>
                <TableCell>{r.skill}</TableCell>
                <TableCell>
                  <Badge variant={statusBadge(r.status)}>{r.status}</Badge>
                </TableCell>
                <TableCell>
                  <span className="text-xs">{stage}</span>
                </TableCell>
                <TableCell>
                  {(r.status === 'running' || r.status === 'pending') && (
                    <Button size="sm" variant="danger" onClick={() => abortOrchestrator(r.run_id)}>
                      Abort
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            )
          })
        )}
      </Table>

      {selectedRun ? <ChipAutomationRunDetail run={selectedRun} /> : null}
    </>
  )
}

function ChipAutomationRunDetail({ run }: { run: ReturnType<typeof useAppStore.getState>['orchestratorRuns'][number] }) {
  const events = run.progress_events || []
  const latest = events[events.length - 1]
  const progressPct = run.stage_total
    ? Math.min(100, Math.round(((run.stage_index || 0) / run.stage_total) * 100))
    : events.length
      ? 100
      : 0

  return (
    <div className="space-y-3">
      <Card
        header={
          <div className="flex items-center justify-between gap-3">
            <span>Chip Automation Command Center</span>
            <Badge variant={statusBadge(run.status)}>{run.status}</Badge>
          </div>
        }
      >
        <div className="space-y-3">
          <div className="grid grid-cols-1 lg:grid-cols-4 gap-3 text-sm">
            <Metric label="Run" value={run.run_id} mono />
            <Metric label="Skill" value={run.skill} />
            <Metric label="Current" value={run.current_stage || latest?.phase || '—'} />
            <Metric label="Progress" value={`${progressPct}%`} mono />
          </div>
          {(run.intent || run.route_rationale) && (
            <div className="rounded-md border border-[var(--color-border-muted)] bg-[var(--color-bg-root)] p-2 text-xs">
              <div className="text-[var(--color-text-secondary)] mb-1">Route Decision</div>
              {run.route_rationale && (
                <div className="text-[var(--color-text)] mb-1">{run.route_rationale}</div>
              )}
              {run.intent && (
                <pre className="m-0 max-h-28 overflow-y-auto text-[var(--color-text-dim)]">
                  {JSON.stringify(run.intent, null, 2)}
                </pre>
              )}
            </div>
          )}
          <div className="h-2 rounded-full bg-[var(--color-bg-root)] overflow-hidden border border-[var(--color-border-muted)]">
            <div
              className="h-full bg-[var(--color-accent)] transition-all"
              style={{ width: `${progressPct}%` }}
            />
          </div>
          {run.error && (
            <div className="text-xs text-[var(--color-danger)] border border-[var(--color-danger)]/30 rounded-md p-2">
              {run.error}
            </div>
          )}
        </div>
      </Card>

      {(run.agent_plan || []).length > 0 && (
        <Card header="Agent DAG">
          <div className="flex flex-wrap items-center gap-2">
            {(run.agent_plan || []).map((step, idx) => (
              <div key={`${step.role_id}-${step.phase}-${idx}`} className="flex items-center gap-2">
                <div className="px-2 py-1 rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-xs">
                  <div className="font-medium text-[var(--color-text)]">{step.role_id || '?'}</div>
                  <div className="text-[var(--color-text-dim)]">{step.phase || 'phase'}</div>
                </div>
                {idx < (run.agent_plan || []).length - 1 && (
                  <span className="text-[var(--color-text-dim)]">→</span>
                )}
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className="grid grid-cols-1 xl:grid-cols-[1.5fr_1fr] gap-3">
        <Card header="Live Timeline">
          <div className="max-h-80 overflow-y-auto space-y-2">
            {events.length ? (
              events.slice(-80).map((evt, idx) => (
                <div key={`${evt.timestamp}-${idx}`} className="grid grid-cols-[92px_1fr] gap-3 text-xs">
                  <div className="text-[var(--color-text-dim)] font-mono">{formatTime(evt.timestamp)}</div>
                  <div className="border-l border-[var(--color-border)] pl-3 pb-2">
                    <div className="flex flex-wrap items-center gap-1">
                      <Badge variant={eventBadge(evt.status || evt.event_type)}>{evt.status || evt.event_type}</Badge>
                      <span className="font-medium">{evt.agent || evt.skill || 'chip'}</span>
                      <span className="text-[var(--color-text-dim)]">{evt.phase || evt.skill || evt.event_type}</span>
                    </div>
                    {evt.message && <div className="text-[var(--color-text-secondary)] mt-1">{evt.message}</div>}
                  </div>
                </div>
              ))
            ) : (
              <div className="text-sm text-[var(--color-text-dim)]">Waiting for structured chip progress…</div>
            )}
          </div>
        </Card>

        <Card header="Evidence">
          <div className="space-y-3 text-xs">
            <EvidenceBlock title="QoR" data={run.qor_summary} />
            <EvidenceBlock title="Coverage" data={run.coverage_summary} />
            <EvidenceBlock title="Fix Requests" data={run.fix_requests} />
            <div>
              <div className="text-[var(--color-text-secondary)] mb-1">Artifacts</div>
              <div className="max-h-28 overflow-y-auto space-y-1 font-mono">
                {(run.artifact_index || []).length ? (
                  (run.artifact_index || []).slice(-20).map((a) => (
                    <div key={a} className="truncate text-[var(--color-text-dim)]">{a}</div>
                  ))
                ) : (
                  <div className="text-[var(--color-text-dim)]">—</div>
                )}
              </div>
            </div>
          </div>
        </Card>
      </div>

      <Card header={`Logs — ${run.run_id}`}>
        <pre className="text-xs font-mono whitespace-pre-wrap max-h-64 overflow-y-auto text-[var(--color-text-secondary)] m-0">
          {(run.logs || []).length
            ? (run.logs || []).join('\n\n')
            : run.status === 'running' || run.status === 'pending'
              ? 'Running — waiting for output...'
              : '(no logs)'}
        </pre>
      </Card>
    </div>
  )
}

function Metric({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-xs text-[var(--color-text-dim)]">{label}</div>
      <div className={`truncate text-[var(--color-text)] ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  )
}

function EvidenceBlock({ title, data }: { title: string; data?: unknown }) {
  const empty =
    data == null ||
    (Array.isArray(data) && data.length === 0) ||
    (!Array.isArray(data) && typeof data === 'object' && Object.keys(data as Record<string, unknown>).length === 0)
  return (
    <div>
      <div className="text-[var(--color-text-secondary)] mb-1">{title}</div>
      <pre className="max-h-28 overflow-y-auto rounded-md bg-[var(--color-bg-root)] border border-[var(--color-border-muted)] p-2 m-0 text-[var(--color-text-dim)]">
        {empty ? '—' : JSON.stringify(data, null, 2)}
      </pre>
    </div>
  )
}

function eventBadge(status?: string) {
  if (status === 'PASS' || status === 'completed' || status === 'run_completed') return 'success'
  if (status === 'FAIL' || status === 'failed' || status === 'run_failed') return 'danger'
  if (status === 'running') return 'warning'
  return 'muted'
}

function formatTime(ts?: string) {
  if (!ts) return '—'
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ts.slice(11, 19)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function statusBadge(status?: string) {
  if (status === 'running' || status === 'pending') return 'warning'
  if (status === 'completed') return 'success'
  if (status === 'failed' || status === 'aborted') return 'danger'
  return 'muted'
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-[var(--color-text-secondary)] mb-1">{label}</label>
      {children}
    </div>
  )
}

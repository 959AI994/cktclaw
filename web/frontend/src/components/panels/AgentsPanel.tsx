import { useMemo, useState } from 'react'
import { useAppStore } from '../../store/appStore'
import { agentId } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
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

      {selectedRun ? (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-elevated)] p-3">
          <div className="text-xs text-[var(--color-text-secondary)] mb-2">
            Logs — {selectedRun.run_id}
            {selectedRun.error ? ` · Error: ${selectedRun.error}` : ''}
          </div>
          <pre className="text-xs font-mono whitespace-pre-wrap max-h-64 overflow-y-auto text-[var(--color-text-secondary)]">
            {(selectedRun.logs || []).length
              ? (selectedRun.logs || []).join('\n\n')
              : selectedRun.status === 'running' || selectedRun.status === 'pending'
                ? 'Running — waiting for output...'
                : '(no logs)'}
          </pre>
        </div>
      ) : null}
    </>
  )
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

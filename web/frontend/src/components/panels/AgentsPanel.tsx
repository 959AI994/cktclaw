import { useAppStore } from '../../store/appStore'
import { agentId } from '../../lib/utils'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { Table, TableRow, TableCell } from '../ui/Table'

export function AgentsPanel() {
  const agents = useAppStore((s) => s.agents)
  const fetchAgents = useAppStore((s) => s.fetchAgents)
  const stopAgent = useAppStore((s) => s.stopAgent)
  const viewAgent = useAppStore((s) => s.viewAgent)
  const showSpawn = useAppStore((s) => s.showSpawn)
  const setShowSpawn = useAppStore((s) => s.setShowSpawn)
  const spawnForm = useAppStore((s) => s.spawnForm)
  const setSpawnForm = useAppStore((s) => s.setSpawnForm)
  const spawnAgent = useAppStore((s) => s.spawnAgent)

  const statusBadge = (status?: string) => {
    if (status === 'running') return 'warning'
    if (status === 'completed') return 'success'
    if (status === 'failed') return 'danger'
    return 'muted'
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Agents</h2>
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
          <input
            className="field-input"
            placeholder="auto"
            value={spawnForm.model}
            onChange={(e) => setSpawnForm({ model: e.target.value })}
          />
        </FormField>
      </Modal>
    </div>
  )
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-[var(--color-text-secondary)] mb-1">{label}</label>
      {children}
    </div>
  )
}

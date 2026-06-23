import { useAppStore } from '../../store/appStore'
import { sessionId, timeAgo } from '../../lib/utils'
import { Button } from '../ui/Button'
import { Table, TableRow, TableCell } from '../ui/Table'

export function SessionsPanel() {
  const sessions = useAppStore((s) => s.sessions)
  const fetchSessions = useAppStore((s) => s.fetchSessions)
  const viewSession = useAppStore((s) => s.viewSession)
  const deleteSession = useAppStore((s) => s.deleteSession)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Sessions</h2>
      <Button size="sm" onClick={fetchSessions}>
        ↻ Refresh
      </Button>

      <Table headers={['ID', 'Created', 'Messages', '']} colWidths={['', '', '', '120px']}>
        {!sessions.length ? (
          <TableRow>
            <TableCell className="text-[var(--color-text-dim)]" colSpan={4}>
              No sessions yet.
            </TableCell>
          </TableRow>
        ) : (
          sessions.map((s) => {
            const id = sessionId(s)
            return (
              <TableRow key={id}>
                <TableCell>
                  <code className="text-xs">{id}</code>
                </TableCell>
                <TableCell>
                  <span className="text-xs text-[var(--color-text-secondary)]">{timeAgo(s.created_at)}</span>
                </TableCell>
                <TableCell>{s.message_count ?? '—'}</TableCell>
                <TableCell>
                  <div className="flex gap-1">
                    <Button size="sm" onClick={() => viewSession(id)}>
                      View
                    </Button>
                    <Button size="sm" variant="danger" onClick={() => deleteSession(id)}>
                      Del
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            )
          })
        )}
      </Table>
    </div>
  )
}

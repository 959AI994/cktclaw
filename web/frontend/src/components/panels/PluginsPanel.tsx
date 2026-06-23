import { useAppStore } from '../../store/appStore'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState } from '../ui/EmptyState'
import { Modal } from '../ui/Modal'

export function PluginsPanel() {
  const plugins = useAppStore((s) => s.plugins)
  const pluginsLoading = useAppStore((s) => s.pluginsLoading)
  const reloadPlugins = useAppStore((s) => s.reloadPlugins)
  const fetchPlugins = useAppStore((s) => s.fetchPlugins)
  const showInstall = useAppStore((s) => s.showInstall)
  const setShowInstall = useAppStore((s) => s.setShowInstall)
  const installForm = useAppStore((s) => s.installForm)
  const setInstallForm = useAppStore((s) => s.setInstallForm)
  const installPlugin = useAppStore((s) => s.installPlugin)

  const statusBadge = (status?: string) => {
    if (status === 'active' || status === 'loaded') return 'success'
    if (status === 'error') return 'danger'
    return 'muted'
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Plugins</h2>

      <p className="text-xs text-[var(--color-text-dim)]">
        Plugins load from <code className="px-1 rounded bg-[var(--color-bg-overlay)]">~/.cktclaw/plugins/</code> and{' '}
        <code className="px-1 rounded bg-[var(--color-bg-overlay)]">.cktclaw/plugins/</code>
      </p>

      <div className="flex gap-2">
        <Button variant="primary" onClick={() => setShowInstall(true)}>
          + Install
        </Button>
        <Button size="sm" onClick={reloadPlugins} disabled={pluginsLoading}>
          ↻ Reload
        </Button>
      </div>

      {pluginsLoading ? (
        <EmptyState variant="loading" title="Loading plugins…" />
      ) : !plugins.length ? (
        <EmptyState
          variant="empty"
          title="No plugins loaded"
          description="Install a plugin from Git or a local path to extend CktClaw."
          onRefresh={fetchPlugins}
        />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {plugins.map((p) => (
            <Card key={p.name} className="p-3.5">
              <div className="flex items-center justify-between mb-2">
                <strong className="font-[family-name:var(--font-mono)] text-sm">{p.name}</strong>
                <Badge variant={statusBadge(p.status)}>{p.status || '?'}</Badge>
              </div>
              <div className="text-sm text-[var(--color-text-secondary)]">
                v{p.version || '?'} — {p.description || 'No description'}
              </div>
              {p.author && <div className="text-[0.72rem] text-[var(--color-text-dim)] mt-2">by {p.author}</div>}
              {p.error_message && (
                <div className="mt-2 text-xs text-[var(--color-danger)] bg-red-500/10 rounded px-2 py-1">
                  {p.error_message}
                </div>
              )}
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={showInstall}
        onClose={() => setShowInstall(false)}
        title="⎔ Install Plugin"
        actions={
          <>
            <Button onClick={() => setShowInstall(false)}>Cancel</Button>
            <Button variant="primary" onClick={installPlugin}>
              Install
            </Button>
          </>
        }
      >
        <div>
          <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Git URL</label>
          <input
            className="field-input"
            placeholder="https://github.com/user/plugin"
            value={installForm.git_url}
            onChange={(e) => setInstallForm({ git_url: e.target.value })}
          />
        </div>
        <div className="text-sm text-[var(--color-text-dim)] text-center">— or —</div>
        <div>
          <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Local Path</label>
          <input
            className="field-input"
            placeholder="/path/to/plugin"
            value={installForm.source_path}
            onChange={(e) => setInstallForm({ source_path: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  )
}

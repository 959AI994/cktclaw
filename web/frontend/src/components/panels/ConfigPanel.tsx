import { useAppStore } from '../../store/appStore'
import { Button } from '../ui/Button'

export function ConfigPanel() {
  const configText = useAppStore((s) => s.configText)
  const setConfigText = useAppStore((s) => s.setConfigText)
  const fetchConfig = useAppStore((s) => s.fetchConfig)
  const saveConfig = useAppStore((s) => s.saveConfig)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Raw Config</h2>
      <p className="text-sm text-[var(--color-text-secondary)]">
        Direct YAML editor for{' '}
        <code className="text-xs px-1 py-0.5 rounded bg-[var(--color-bg-overlay)]">~/.cktclaw/config.yaml</code>
      </p>

      <div className="flex gap-2">
        <Button variant="primary" onClick={saveConfig}>
          Save
        </Button>
        <Button size="sm" onClick={fetchConfig}>
          ↻ Reload
        </Button>
      </div>

      <textarea
        spellCheck={false}
        className="w-full min-h-[55vh] font-[family-name:var(--font-mono)] text-[0.72rem] bg-[var(--color-bg-root)] text-[var(--color-text)] border border-[var(--color-border)] rounded-[10px] p-4 resize-y outline-none focus:border-[var(--color-accent)]"
        placeholder="Loading config…"
        value={configText}
        onChange={(e) => setConfigText(e.target.value)}
      />

      <p className="text-sm text-[var(--color-text-dim)]">
        Changes take effect after restarting CktClaw or switching models.
      </p>
    </div>
  )
}

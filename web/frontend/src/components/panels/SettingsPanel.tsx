import { useAppStore } from '../../store/appStore'
import { ProviderCard } from '../settings/ProviderCard'

export function SettingsPanel() {
  const providers = useAppStore((s) => s.providers)

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold">Settings</h2>
      <p className="text-sm text-[var(--color-text-secondary)]">
        Configure LLM providers, API keys, and model preferences. Keys are saved to{' '}
        <code className="text-xs px-1 py-0.5 rounded bg-[var(--color-bg-overlay)]">~/.cktclaw/config.yaml</code>.
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Object.entries(providers).length === 0 ? (
          <div className="text-sm text-[var(--color-text-dim)]">No providers configured.</div>
        ) : (
          Object.entries(providers).map(([name, p]) => <ProviderCard key={name} name={name} provider={p} />)
        )}
      </div>
    </div>
  )
}

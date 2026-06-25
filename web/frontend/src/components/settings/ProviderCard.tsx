import { useState } from 'react'
import type { ProviderInfo } from '../../types/api'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card } from '../ui/Card'
import { useAppStore } from '../../store/appStore'

interface ProviderCardProps {
  name: string
  provider: ProviderInfo
}

export function ProviderCard({ name, provider: p }: ProviderCardProps) {
  const saveProvider = useAppStore((s) => s.saveProvider)
  const switchModel = useAppStore((s) => s.switchModel)
  const toast = useAppStore((s) => s.toast)

  const [apiKey, setApiKey] = useState('')
  const [baseUrl, setBaseUrl] = useState(p.base_url || '')
  const [model, setModel] = useState(p.current_model || p.available_models?.[0] || '')
  const [showKey, setShowKey] = useState(false)

  const handleSave = () => {
    const updates: { api_key?: string; base_url?: string; model?: string } = {}
    if (apiKey.trim()) updates.api_key = apiKey.trim()
    if (baseUrl.trim()) updates.base_url = baseUrl.trim()
    if (model) updates.model = model
    saveProvider(name, updates).then(() => {
      if (apiKey) setApiKey('')
    })
  }

  const handleTest = async () => {
    try {
      const res = await fetch('/api/status')
      if (res.ok) toast('success', `${name} is responding`)
      else toast('error', 'Connection issue')
    } catch (e) {
      toast('error', e instanceof Error ? e.message : 'Failed')
    }
  }

  return (
    <Card className="p-4">
      <div className="flex items-center justify-between mb-4">
        <span className="font-semibold">{p.label}</span>
        <div className="flex gap-1">
          <Badge variant={p.is_available ? 'success' : 'muted'}>{p.is_available ? 'available' : 'no key'}</Badge>
          {p.is_current && <Badge variant="accent">active</Badge>}
        </div>
      </div>

      <div className="space-y-3">
        <div>
          <label className="block text-xs text-[var(--color-text-secondary)] mb-1">API Key</label>
          <div className="flex gap-1">
            <input
              type={showKey ? 'text' : 'password'}
              className="flex-1 px-3 py-1.5 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
              placeholder={p.has_key ? '•••••••• (saved)' : 'sk-...'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              autoComplete="off"
            />
            <button
              type="button"
              className="px-2 opacity-60 hover:opacity-100"
              onClick={() => setShowKey(!showKey)}
            >
              👁
            </button>
          </div>
          <p className="text-[0.72rem] text-[var(--color-text-dim)] mt-1">
            {p.has_key
              ? `Key saved in ${p.key_source === 'env' ? 'environment' : '~/.cktclaw/config.yaml'}`
              : 'No key configured'}
          </p>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Base URL</label>
            <input
              type="url"
              className="w-full px-3 py-1.5 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)] outline-none focus:border-[var(--color-accent)]"
              placeholder={p.base_url || p.default_base_url || 'https://api...'}
              value={baseUrl}
              onChange={(e) => setBaseUrl(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-[var(--color-text-secondary)] mb-1">Model</label>
            <select
              className="w-full px-3 py-1.5 text-sm rounded-md border border-[var(--color-border)] bg-[var(--color-bg-root)] text-[var(--color-text)]"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              {(p.available_models || []).map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-2">
          <Button variant="primary" size="sm" onClick={handleSave}>
            Save
          </Button>
          {!p.is_current && p.is_available && (
            <Button variant="success" size="sm" onClick={() => switchModel(name)}>
              Activate
            </Button>
          )}
          {p.is_current && (
            <Button variant="primary" size="sm" onClick={handleTest}>
              Test
            </Button>
          )}
        </div>
      </div>
    </Card>
  )
}

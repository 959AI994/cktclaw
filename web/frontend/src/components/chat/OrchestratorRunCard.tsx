import { useState } from 'react'
import type { ActiveOrchestratorRun } from '../../types/api'
import { Badge } from '../ui/Badge'

interface OrchestratorRunCardProps {
  run: ActiveOrchestratorRun
}

function statusVariant(status: ActiveOrchestratorRun['status']) {
  if (status === 'completed') return 'success' as const
  if (status === 'failed' || status === 'aborted') return 'danger' as const
  return 'accent' as const
}

export function OrchestratorRunCard({ run }: OrchestratorRunCardProps) {
  const [logsExpanded, setLogsExpanded] = useState(true)

  const isChipSystem = run.skill === 'chip-system'

  const stageLabel =
    run.stage && run.stage_total
      ? `${run.stage} (${run.stage_index ?? '?'}/${run.stage_total})`
      : run.stage || '—'

  const isRunning = run.status === 'running'

  const title = isRunning
    ? isChipSystem
      ? '七 Agent 流水线运行中'
      : 'Orchestrator 运行中'
    : run.status === 'completed'
      ? isChipSystem
        ? '七 Agent 流水线已完成'
        : 'Orchestrator 已完成'
      : isChipSystem
        ? '七 Agent 流水线失败'
        : 'Orchestrator 失败'

  return (
    <div className="mx-1 my-3 p-4 rounded-xl border border-[var(--color-accent)]/30 bg-[var(--color-bg-overlay)]">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-start gap-2 min-w-0">
          {isRunning && (
            <span className="inline-block w-4 h-4 mt-0.5 border-2 border-[var(--color-accent)] border-t-transparent rounded-full animate-spin shrink-0" />
          )}
          <div className="min-w-0">
            <h4 className="text-sm font-semibold text-[var(--color-text)] m-0">{title}</h4>
            <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 mb-0 truncate">
              {run.skill} · <span className="font-mono">{run.run_id}</span>
            </p>
          </div>
        </div>
        <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
      </div>

      {run.task && (
        <p className="text-xs text-[var(--color-text-dim)] mb-2 line-clamp-2">{run.task}</p>
      )}

      {isChipSystem && isRunning && (
        <p className="text-xs text-[var(--color-text-dim)] mb-2">
          PM → Architect → EDA → Compiler∥Runtime → Deploy → Optimizer
        </p>
      )}

      <dl className="text-xs grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 mb-3">
        <dt className="text-[var(--color-text-dim)]">{isChipSystem ? 'Phase' : 'Stage'}</dt>
        <dd className="text-[var(--color-text)] m-0 font-medium">{stageLabel}</dd>
      </dl>

      {run.status === 'completed' && run.summary && (
        <div className="mb-3 p-2 rounded-lg bg-[var(--color-bg-root)] border border-[var(--color-border)]">
          <div className="text-xs text-[var(--color-text-dim)] mb-1">结果摘要</div>
          <pre className="text-xs whitespace-pre-wrap max-h-48 overflow-y-auto m-0 text-[var(--color-text-secondary)]">
            {run.summary}
          </pre>
        </div>
      )}

      {(run.status === 'failed' || run.status === 'aborted') && run.error && (
        <div className="mb-3 p-2 rounded-lg bg-[var(--color-danger)]/10 border border-[var(--color-danger)]/30 text-xs text-[var(--color-danger)]">
          {run.error}
        </div>
      )}

      <div>
        <button
          type="button"
          className="text-xs text-[var(--color-accent)] hover:underline mb-1"
          onClick={() => setLogsExpanded((v) => !v)}
        >
          {logsExpanded ? '收起日志' : '展开日志'} ({run.logs.length})
        </button>
        {logsExpanded && (
          <pre className="text-xs font-mono whitespace-pre-wrap max-h-52 overflow-y-auto p-2 rounded-lg bg-[var(--color-bg-root)] border border-[var(--color-border)] text-[var(--color-text-secondary)] m-0">
            {run.logs.length
              ? run.logs.join('\n\n')
              : isRunning
                ? 'Running — waiting for output...'
                : '(no logs)'}
          </pre>
        )}
      </div>
    </div>
  )
}

import { useState } from 'react'
import type { OrchestratorProposal } from '../../types/api'
import { Button } from '../ui/Button'

interface OrchestratorProposalCardProps {
  proposal: OrchestratorProposal
  onConfirm: (task: string) => void
  onCancel: () => void
}

export function OrchestratorProposalCard({ proposal, onConfirm, onCancel }: OrchestratorProposalCardProps) {
  const [editing, setEditing] = useState(false)
  const [taskDraft, setTaskDraft] = useState(proposal.task)

  const confPct = Math.round((proposal.confidence || 0) * 100)

  return (
    <div className="mx-4 my-3 p-4 rounded-xl border border-[var(--color-purple)]/40 bg-[var(--color-bg-overlay)]">
      <div className="flex items-start gap-2 mb-2">
        <span className="text-lg">⚡</span>
        <div>
          <h4 className="text-sm font-semibold text-[var(--color-text)] m-0">Orchestrator 执行计划</h4>
          <p className="text-xs text-[var(--color-text-secondary)] mt-0.5 mb-0">
            检测到芯片设计意图 · 置信度 {confPct}%
          </p>
        </div>
      </div>

      <dl className="text-xs space-y-1.5 mb-3">
        <div className="flex gap-2">
          <dt className="text-[var(--color-text-dim)] w-16 shrink-0">Skill</dt>
          <dd className="text-[var(--color-text)] m-0 font-medium">{proposal.skill}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[var(--color-text-dim)] w-16 shrink-0">任务</dt>
          <dd className="text-[var(--color-text)] m-0">
            {editing ? (
              <textarea
                className="w-full px-2 py-1 rounded border border-[var(--color-border)] bg-[var(--color-bg-root)] text-xs resize-none"
                rows={3}
                value={taskDraft}
                onChange={(e) => setTaskDraft(e.target.value)}
              />
            ) : (
              <span className="whitespace-pre-wrap">{proposal.task}</span>
            )}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-[var(--color-text-dim)] w-16 shrink-0">预估</dt>
          <dd className="text-[var(--color-text-secondary)] m-0">
            ~{proposal.estimated_stages ?? 6} 阶段 · ~{proposal.estimated_minutes ?? 5} 分钟
          </dd>
        </div>
      </dl>

      <div className="flex flex-wrap gap-2">
        <Button variant="primary" size="sm" onClick={() => onConfirm(editing ? taskDraft : proposal.task)}>
          确认执行
        </Button>
        <Button
          variant="default"
          size="sm"
          onClick={() => {
            if (editing) {
              onConfirm(taskDraft)
            } else {
              setEditing(true)
            }
          }}
        >
          {editing ? '保存并执行' : '修改参数'}
        </Button>
        <Button variant="default" size="sm" onClick={onCancel}>
          取消
        </Button>
      </div>
    </div>
  )
}

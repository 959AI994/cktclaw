import type { ReactNode } from 'react'

interface TableProps {
  headers: string[]
  children: ReactNode
  colWidths?: string[]
}

export function Table({ headers, children, colWidths }: TableProps) {
  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--color-border)]">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-[var(--color-bg-overlay)] text-left text-[var(--color-text-secondary)]">
            {headers.map((h, i) => (
              <th key={h} className="px-3 py-2 font-medium" style={colWidths?.[i] ? { width: colWidths[i] } : undefined}>
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-[var(--color-border-muted)]">{children}</tbody>
      </table>
    </div>
  )
}

export function TableRow({ children }: { children: ReactNode }) {
  return <tr className="hover:bg-[var(--color-bg-overlay)]/50">{children}</tr>
}

export function TableCell({
  children,
  className = '',
  colSpan,
}: {
  children: ReactNode
  className?: string
  colSpan?: number
}) {
  return (
    <td className={`px-3 py-2 align-middle ${className}`} colSpan={colSpan}>
      {children}
    </td>
  )
}

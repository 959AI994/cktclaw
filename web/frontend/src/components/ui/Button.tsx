import type { ButtonHTMLAttributes, ReactNode } from 'react'

const variants: Record<string, string> = {
  default: 'bg-[var(--color-bg-overlay)] text-[var(--color-text)] hover:bg-[var(--color-border)] border border-[var(--color-border)]',
  primary: 'bg-[var(--color-accent)] text-white hover:opacity-90 border border-transparent',
  success: 'bg-[var(--color-success)] text-white hover:opacity-90 border border-transparent',
  danger: 'bg-[var(--color-danger)] text-white hover:opacity-90 border border-transparent',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof variants
  size?: 'sm' | 'md'
  children: ReactNode
}

export function Button({ variant = 'default', size = 'md', children, className = '', ...props }: ButtonProps) {
  const sizeCls = size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3.5 py-1.5 text-sm'
  return (
    <button
      className={`inline-flex items-center justify-center rounded-md font-medium transition-opacity disabled:opacity-40 cursor-pointer ${variants[variant]} ${sizeCls} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

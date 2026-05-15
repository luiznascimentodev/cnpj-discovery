import { cn } from '@/shared/lib'

export function Kbd({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <kbd
      className={cn(
        'inline-flex items-center rounded border border-[var(--color-border)] bg-[var(--color-bg-subtle)]',
        'px-1.5 h-5 text-[10px] text-[var(--color-fg-secondary)] font-medium font-mono',
        className
      )}
    >
      {children}
    </kbd>
  )
}

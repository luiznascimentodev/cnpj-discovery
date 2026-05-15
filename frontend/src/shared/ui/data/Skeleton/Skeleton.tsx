import { cn } from '@/shared/lib'

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      role="status"
      aria-label="Carregando"
      className={cn('animate-pulse bg-[var(--color-gray-200)] rounded-md', className)}
    />
  )
}

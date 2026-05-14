import * as AlertDialog from '@radix-ui/react-alert-dialog'
import { forwardRef } from 'react'
import { cn } from '@/shared/lib'

export const AlertDialogRoot = AlertDialog.Root
export const AlertDialogTrigger = AlertDialog.Trigger
export const AlertDialogAction = AlertDialog.Action
export const AlertDialogCancel = AlertDialog.Cancel
export const AlertDialogTitle = AlertDialog.Title
export const AlertDialogDescription = AlertDialog.Description

export const AlertDialogContent = forwardRef<
  React.ElementRef<typeof AlertDialog.Content>,
  React.ComponentPropsWithoutRef<typeof AlertDialog.Content>
>(({ className, ...props }, ref) => (
  <AlertDialog.Portal>
    <AlertDialog.Overlay className="fixed inset-0 bg-black/40 z-[var(--z-modal-backdrop)]" />
    <AlertDialog.Content
      ref={ref}
      className={cn(
        'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[var(--z-modal)] max-w-md w-full',
        'bg-[var(--color-bg-surface)] rounded-xl shadow-[var(--shadow-lg)] p-6 focus:outline-none',
        className
      )}
      {...props}
    />
  </AlertDialog.Portal>
))
AlertDialogContent.displayName = 'AlertDialogContent'

import * as Dialog from '@radix-ui/react-dialog'
import { forwardRef } from 'react'
import { cva, type VariantProps } from 'class-variance-authority'
import { X } from '@/shared/ui/icons'
import { cn } from '@/shared/lib'

const contentVariants = cva(
  'fixed left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-[var(--z-modal)] ' +
  'bg-[var(--color-bg-surface)] rounded-xl shadow-[var(--shadow-lg)] p-6 ' +
  'data-[state=open]:animate-in data-[state=closed]:animate-out ' +
  'focus:outline-none w-full',
  {
    variants: {
      size: {
        sm: 'max-w-md',
        md: 'max-w-lg',
        lg: 'max-w-2xl',
        xl: 'max-w-4xl',
        fullscreen: 'max-w-none w-screen h-screen rounded-none',
      },
    },
    defaultVariants: { size: 'md' },
  }
)

export const DialogRoot = Dialog.Root
export const DialogTrigger = Dialog.Trigger
export const DialogClose = Dialog.Close

export const DialogContent = forwardRef<
  React.ElementRef<typeof Dialog.Content>,
  React.ComponentPropsWithoutRef<typeof Dialog.Content> & VariantProps<typeof contentVariants>
>(({ className, size, children, ...props }, ref) => (
  <Dialog.Portal>
    <Dialog.Overlay className="fixed inset-0 bg-black/40 z-[var(--z-modal-backdrop)] data-[state=open]:animate-in data-[state=closed]:animate-out" />
    <Dialog.Content ref={ref} className={cn(contentVariants({ size }), className)} {...props}>
      {children}
      <Dialog.Close
        aria-label="Fechar"
        className="absolute right-3 top-3 p-1.5 rounded-md hover:bg-[var(--color-bg-subtle)] focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]"
      >
        <X size={16} aria-hidden="true" />
      </Dialog.Close>
    </Dialog.Content>
  </Dialog.Portal>
))
DialogContent.displayName = 'DialogContent'

export const DialogTitle = forwardRef<
  React.ElementRef<typeof Dialog.Title>,
  React.ComponentPropsWithoutRef<typeof Dialog.Title>
>(({ className, ...props }, ref) => (
  <Dialog.Title ref={ref} className={cn('text-[var(--text-lg)] font-semibold leading-tight', className)} {...props} />
))
DialogTitle.displayName = 'DialogTitle'

export const DialogDescription = forwardRef<
  React.ElementRef<typeof Dialog.Description>,
  React.ComponentPropsWithoutRef<typeof Dialog.Description>
>(({ className, ...props }, ref) => (
  <Dialog.Description ref={ref} className={cn('text-[var(--text-sm)] text-[var(--color-fg-secondary)] mt-1', className)} {...props} />
))
DialogDescription.displayName = 'DialogDescription'

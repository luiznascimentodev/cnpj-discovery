import { Command } from 'cmdk'
import { useState } from 'react'
import { PopoverRoot, PopoverTrigger, PopoverContent } from '../Popover/Popover'
import { cn } from '@/shared/lib'

export interface ComboboxOption {
  value: string
  label: string
}

export interface ComboboxProps {
  options: ComboboxOption[]
  value?: string
  onChange?: (v: string) => void
  onSearchChange?: (q: string) => void
  placeholder?: string
  emptyText?: string
  loading?: boolean
}

export function Combobox({
  options,
  value,
  onChange,
  onSearchChange,
  placeholder = 'Buscar…',
  emptyText = 'Nada encontrado.',
  loading = false,
}: ComboboxProps) {
  const [open, setOpen] = useState(false)
  const selected = options.find((o) => o.value === value)

  return (
    <PopoverRoot open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          role="combobox"
          aria-expanded={open}
          className={cn(
            'flex h-10 w-full items-center justify-between rounded-md border border-[var(--color-border-strong)]',
            'bg-[var(--color-bg-surface)] px-3 text-left text-[var(--text-base)]',
            'focus-visible:outline-none focus-visible:shadow-[var(--shadow-focus)]'
          )}
        >
          {selected ? selected.label : <span className="text-[var(--color-fg-muted)]">{placeholder}</span>}
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-[var(--radix-popover-trigger-width)] p-0">
        <Command shouldFilter={!onSearchChange} loop>
          <Command.Input
            onValueChange={onSearchChange}
            placeholder={placeholder}
            className="w-full border-b border-[var(--color-border)] px-3 py-2 outline-none text-[var(--text-sm)]"
          />
          <Command.List className="max-h-60 overflow-auto p-1">
            {loading && (
              <div className="px-2 py-2 text-[var(--text-xs)] text-[var(--color-fg-muted)]">Carregando…</div>
            )}
            {!loading && (
              <Command.Empty className="px-2 py-2 text-[var(--text-xs)] text-[var(--color-fg-muted)]">
                {emptyText}
              </Command.Empty>
            )}
            {options.map((o) => (
              <Command.Item
                key={o.value}
                value={o.value}
                onSelect={() => {
                  onChange?.(o.value)
                  setOpen(false)
                }}
                className="px-2 py-2 rounded-md text-[var(--text-sm)] aria-selected:bg-[var(--color-bg-subtle)] cursor-pointer"
              >
                {o.label}
              </Command.Item>
            ))}
          </Command.List>
        </Command>
      </PopoverContent>
    </PopoverRoot>
  )
}

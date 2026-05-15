import { flexRender, getCoreRowModel, useReactTable, type ColumnDef } from '@tanstack/react-table'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useRef } from 'react'
import { cn } from '@/shared/lib'

export interface DataTableProps<T> {
  data: T[]
  columns: ColumnDef<T, unknown>[]
  rowKey: (row: T) => string
  emptyMessage?: string
  loading?: boolean
  estimatedRowHeight?: number
  maxHeight?: number
  className?: string
}

export function DataTable<T>({
  data,
  columns,
  rowKey,
  emptyMessage = 'Nenhum resultado.',
  loading,
  estimatedRowHeight = 36,
  maxHeight = 600,
  className,
}: DataTableProps<T>) {
  const table = useReactTable({
    data,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (r) => rowKey(r),
  })
  const rows = table.getRowModel().rows
  const parentRef = useRef<HTMLDivElement>(null)
  const rowVirtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => estimatedRowHeight,
    overscan: 8,
  })

  return (
    <div
      ref={parentRef}
      className={cn(
        'overflow-auto rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-surface)]',
        className
      )}
      style={{ maxHeight }}
    >
      <table className="w-full text-[var(--text-sm)]" role="table" aria-busy={loading || undefined}>
        <thead className="sticky top-0 z-10 bg-[var(--color-bg-app)]">
          {table.getHeaderGroups().map((hg) => (
            <tr key={hg.id}>
              {hg.headers.map((h) => (
                <th
                  key={h.id}
                  className="text-left font-semibold text-[var(--color-fg-primary)] uppercase tracking-wide text-[var(--text-xs)] px-3 py-2 border-b border-[var(--color-border)]"
                >
                  {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody style={{ height: rowVirtualizer.getTotalSize(), position: 'relative' }}>
          {rows.length === 0 && !loading && (
            <tr>
              <td colSpan={columns.length} className="text-center py-8 text-[var(--color-fg-muted)]">
                {emptyMessage}
              </td>
            </tr>
          )}
          {rowVirtualizer.getVirtualItems().map((virtualRow) => {
            const row = rows[virtualRow.index]
            return (
              <tr
                key={row.id}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualRow.start}px)`,
                  height: virtualRow.size,
                }}
                className="hover:bg-[var(--color-gray-50)] border-b border-[var(--color-gray-100)]"
              >
                {row.getVisibleCells().map((cell) => (
                  <td key={cell.id} className="px-3 align-middle">
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

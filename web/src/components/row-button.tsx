import type { ReactNode } from "react"

/**
 * The keyboard and screen-reader entry point for a clickable table row. Rows stay plain
 * <tr>s so the table keeps its semantics; the row's own onClick is a mouse convenience.
 */
export function RowButton({ label, onClick, children }: { label: string; onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      onClick={(event) => {
        event.stopPropagation()
        onClick()
      }}
      className="-mx-1 rounded-md px-1 text-left font-mono text-[12px] outline-none focus-visible:ring-4 focus-visible:ring-ring"
    >
      {children}
    </button>
  )
}

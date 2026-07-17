import type { ReactNode } from "react"
import { Separator } from "@/components/ui/separator"
import { SidebarTrigger } from "@/components/ui/sidebar"

type Props = {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ title, subtitle, actions }: Props) {
  return (
    <header className="material sticky top-0 z-30 flex h-13 shrink-0 items-center gap-2 border-b border-border/60 px-4">
      <SidebarTrigger className="-ml-1" aria-label="Toggle sidebar" />
      <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
      <div className="flex min-w-0 items-baseline gap-2">
        <h1 className="truncate text-[15px] font-semibold">{title}</h1>
        {subtitle && <span className="hidden truncate text-[13px] text-muted-foreground sm:inline">{subtitle}</span>}
      </div>
      {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
    </header>
  )
}

export function PageBody({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className={wide ? "w-full px-4 py-6 sm:px-6" : "mx-auto w-full max-w-7xl space-y-6 px-4 py-6 sm:px-6 lg:py-8"}>
      {children}
    </div>
  )
}

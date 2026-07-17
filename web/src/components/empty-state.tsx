import type { LucideIcon } from "lucide-react"
import type { ReactNode } from "react"
import { cn } from "@/lib/utils"

type Props = {
  icon: LucideIcon
  title: string
  description: string
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon: Icon, title, description, action, className }: Props) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-20 text-center", className)}>
      <Icon className="mb-4 size-11 text-muted-foreground/60" strokeWidth={1.5} aria-hidden />
      <h2 className="text-[17px] leading-[22px] font-semibold">{title}</h2>
      <p className="mt-1 max-w-sm text-[14px] text-muted-foreground">{description}</p>
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}

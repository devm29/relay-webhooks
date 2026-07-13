import type { ReactNode } from "react"
import { Skeleton } from "@/components/ui/skeleton"
import { cn } from "@/lib/utils"

type Props = {
  label: string
  value: ReactNode
  hint?: ReactNode
  tone?: "default" | "danger" | "success"
  loading?: boolean
}

export function Kpi({ label, value, hint, tone = "default", loading = false }: Props) {
  return (
    <div className="rounded-xl border border-border/60 bg-card p-5 shadow-xs">
      <div className="text-[13px] text-muted-foreground">{label}</div>
      {loading ? (
        <Skeleton className="mt-2 h-8 w-24" />
      ) : (
        <div
          className={cn(
            "mt-1 text-[28px] leading-[34px] font-semibold tracking-tight tabular-nums",
            tone === "danger" && "text-destructive",
            tone === "success" && "text-success-text",
          )}
        >
          {value}
        </div>
      )}
      {hint && <div className="mt-1 text-[12px] text-muted-foreground">{hint}</div>}
    </div>
  )
}

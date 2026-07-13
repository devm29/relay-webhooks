import type { BreakerState, DeliveryStatus, Endpoint } from "@/lib/api/schemas"
import { cn } from "@/lib/utils"

type Tone = "success" | "warning" | "danger" | "neutral" | "info"

const TONES: Record<Tone, { pill: string; dot: string }> = {
  success: { pill: "bg-success/12 text-success-text", dot: "bg-success" },
  warning: { pill: "bg-warning/15 text-warning-text", dot: "bg-warning" },
  danger: { pill: "bg-destructive/10 text-destructive", dot: "bg-destructive" },
  info: { pill: "bg-primary/10 text-primary", dot: "bg-primary" },
  neutral: { pill: "bg-muted text-muted-foreground dark:bg-accent", dot: "bg-muted-foreground" },
}

export function StatusPill({ tone, children, className }: { tone: Tone; children: React.ReactNode; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex h-5 shrink-0 items-center gap-1.5 rounded-full px-2 text-[11px] font-medium whitespace-nowrap",
        TONES[tone].pill,
        className,
      )}
    >
      <span className={cn("size-1.5 rounded-full", TONES[tone].dot)} aria-hidden />
      {children}
    </span>
  )
}

export function StatusDot({ tone, pulse = false }: { tone: Tone; pulse?: boolean }) {
  return (
    <span className="relative inline-flex size-2" aria-hidden>
      {pulse && (
        <span
          className={cn(
            "absolute inline-flex size-full animate-ping rounded-full opacity-60 motion-reduce:animate-none",
            TONES[tone].dot,
          )}
        />
      )}
      <span className={cn("relative inline-flex size-2 rounded-full", TONES[tone].dot)} />
    </span>
  )
}

const DELIVERY: Record<DeliveryStatus, { tone: Tone; label: string }> = {
  succeeded: { tone: "success", label: "Delivered" },
  pending: { tone: "info", label: "Retrying" },
  dead: { tone: "danger", label: "Dead" },
}

export function DeliveryStatusPill({ status }: { status: DeliveryStatus }) {
  const { tone, label } = DELIVERY[status]
  return <StatusPill tone={tone}>{label}</StatusPill>
}

export function HttpStatus({ code, error }: { code: number | null; error?: string | null }) {
  if (code === null) {
    return (
      <span className="font-mono text-[12px] text-destructive" title={error ?? undefined}>
        {error?.startsWith("timed out") ? "timeout" : "error"}
      </span>
    )
  }
  const tone = code < 300 ? "text-success-text" : code < 500 ? "text-warning-text" : "text-destructive"
  return <span className={cn("font-mono text-[12px] font-medium tabular-nums", tone)}>{code}</span>
}

export type EndpointHealth = { tone: Tone; label: string }

const BREAKER: Record<BreakerState, EndpointHealth> = {
  closed: { tone: "success", label: "Healthy" },
  open: { tone: "danger", label: "Circuit open" },
  half_open: { tone: "warning", label: "Probing" },
}

export function endpointHealth(endpoint: Endpoint): EndpointHealth {
  if (endpoint.disabled) return { tone: "neutral", label: "Disabled" }
  return BREAKER[endpoint.breaker?.state ?? "closed"]
}

export function EndpointHealthPill({ endpoint }: { endpoint: Endpoint }) {
  const { tone, label } = endpointHealth(endpoint)
  return <StatusPill tone={tone}>{label}</StatusPill>
}

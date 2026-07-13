"use client"

import { AlertTriangle, Pencil, Power, RotateCcw } from "lucide-react"
import { useParams } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"
import { LatencyChart } from "@/components/charts/latency-chart"
import { SuccessChart } from "@/components/charts/success-chart"
import { DeliverySheet } from "@/components/delivery-sheet"
import { EndpointDialog } from "@/components/endpoint-dialog"
import { Kpi } from "@/components/kpi"
import { QueryError } from "@/components/query-error"
import { Segmented, WINDOW_OPTIONS } from "@/components/segmented"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { EndpointHealthPill, HttpStatus } from "@/components/status"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Switch } from "@/components/ui/switch"
import { errorMessage } from "@/lib/api/client"
import {
  useAttempts,
  useBulkReplay,
  useEnableEndpoint,
  useEndpoint,
  useEndpointStats,
  useMe,
  useUpdateEndpoint,
} from "@/lib/api/hooks"
import type { Endpoint, StatsWindow } from "@/lib/api/schemas"
import { clockTime, count, dateTime, endpointName, latency, percent, timeAgo } from "@/lib/format"
import { SecretCard } from "./secret-card"

export function EndpointDetailView() {
  const { appId, endpointId } = useParams<{ appId: string; endpointId: string }>()
  const [range, setRange] = useState<StatsWindow>("24h")
  const [editing, setEditing] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const endpoint = useEndpoint(appId, endpointId)
  const stats = useEndpointStats(appId, endpointId, range)
  const me = useMe()
  const canWrite = me.data?.scopes.includes("endpoints:write") ?? false
  const canReplay = me.data?.scopes.includes("deliveries:replay") ?? false
  const data = endpoint.data
  const name = data ? endpointName(data) : "Endpoint"

  return (
    <>
      <PageHeader
        title={name}
        actions={
          <>
            {canReplay && <ReplayDeadButton appId={appId} endpointId={endpointId} />}
            {canWrite && data && (
              <Button variant="secondary" size="sm" onClick={() => setEditing(true)}>
                <Pencil /> Edit
              </Button>
            )}
          </>
        }
      />
      <PageBody>
        {endpoint.isError && !data ? (
          <QueryError error={endpoint.error} onRetry={endpoint.refetch} retrying={endpoint.isFetching} />
        ) : data ? (
          <Hero appId={appId} endpoint={data} canWrite={canWrite} />
        ) : (
          <Skeleton className="h-20 w-full" />
        )}

        <div className="flex items-center justify-between">
          <h3 className="text-[17px] font-semibold">Performance</h3>
          <Segmented label="Time range" value={range} options={WINDOW_OPTIONS} onChange={setRange} />
        </div>
        {stats.isError && !stats.data ? (
          <Card>
            <QueryError
              error={stats.error}
              onRetry={stats.refetch}
              retrying={stats.isFetching}
              title="Couldn’t load performance"
            />
          </Card>
        ) : (
          <>
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi label="Success rate" loading={!stats.data} value={percent(stats.data?.success_rate)} />
          <Kpi label="p50 latency" loading={!stats.data} value={latency(stats.data?.p50_ms)} />
          <Kpi label="p95 latency" loading={!stats.data} value={latency(stats.data?.p95_ms)} />
          <Kpi
            label="Attempts"
            loading={!stats.data}
            value={stats.data ? count(stats.data.total) : null}
            hint={stats.data ? `${count(stats.data.failed)} failed` : null}
          />
        </section>
        <section className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Latency</CardTitle>
              <CardDescription>p50 and p95 per interval</CardDescription>
            </CardHeader>
            <CardContent>
              {stats.data ? <LatencyChart series={stats.data.series} window={range} /> : <Skeleton className="h-56" />}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Success rate</CardTitle>
              <CardDescription>Share of attempts answered with 2xx</CardDescription>
            </CardHeader>
            <CardContent>
              {stats.data ? <SuccessChart series={stats.data.series} window={range} /> : <Skeleton className="h-56" />}
            </CardContent>
          </Card>
        </section>
          </>
        )}

        <section className="grid gap-4 lg:grid-cols-5">
          <div className="space-y-4 lg:col-span-2">
            {canWrite && <SecretCard appId={appId} endpointId={endpointId} />}
            {data && <ConfigCard endpoint={data} />}
          </div>
          <RecentAttempts appId={appId} endpointId={endpointId} onSelect={setSelected} />
        </section>
      </PageBody>
      {data && <EndpointDialog key={data.updated_at} appId={appId} endpoint={data} open={editing} onOpenChange={setEditing} />}
      <DeliverySheet appId={appId} deliveryId={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  )
}

function Hero({ appId, endpoint, canWrite }: { appId: string; endpoint: Endpoint; canWrite: boolean }) {
  const enable = useEnableEndpoint(appId, endpoint.id)
  const breaker = endpoint.breaker
  const tripped = breaker && breaker.state !== "closed"

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h2 className="truncate text-[28px] leading-[34px] font-semibold tracking-tight">{endpointName(endpoint)}</h2>
            <EndpointHealthPill endpoint={endpoint} />
          </div>
          <p className="mt-1 truncate font-mono text-[13px] text-muted-foreground">{endpoint.url}</p>
          {endpoint.description && <p className="mt-1 text-[14px] text-muted-foreground">{endpoint.description}</p>}
        </div>
      </div>
      {(endpoint.disabled || tripped) && (
        <div
          role="status"
          className="flex flex-wrap items-center gap-3 rounded-xl border border-destructive/20 bg-destructive/5 px-4 py-3"
        >
          <AlertTriangle className="size-4 shrink-0 text-destructive" />
          <div className="min-w-0 flex-1 text-[13px]">
            {endpoint.disabled ? (
              <>
                <span className="font-medium">Delivery is paused.</span>{" "}
                <span className="text-muted-foreground">
                  {endpoint.disabled_reason ?? "Disabled"}. New messages are not queued for this endpoint.
                </span>
              </>
            ) : (
              <>
                <span className="font-medium">
                  Circuit {breaker?.state === "half_open" ? "is probing" : "is open"}.
                </span>{" "}
                <span className="text-muted-foreground">
                  {breaker?.consecutive_failures} consecutive failures, tripped {breaker?.trip_count}{" "}
                  {breaker?.trip_count === 1 ? "time" : "times"}.
                  {breaker?.open_until && ` Next probe ${timeAgo(breaker.open_until)}.`}
                </span>
              </>
            )}
          </div>
          {canWrite && (
            <Button
              size="sm"
              disabled={enable.isPending}
              onClick={() =>
                enable.mutate(undefined, {
                  onSuccess: () => toast.success("Endpoint enabled and circuit closed"),
                  onError: (error) => toast.error(errorMessage(error)),
                })
              }
            >
              <Power /> {endpoint.disabled ? "Enable" : "Reset circuit"}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

function ConfigCard({ endpoint }: { endpoint: Endpoint }) {
  const update = useUpdateEndpoint(endpoint.app_id, endpoint.id)
  const me = useMe()
  const canWrite = me.data?.scopes.includes("endpoints:write") ?? false
  const headers = Object.entries(endpoint.headers)
  return (
    <Card className="gap-0 py-0">
      <dl className="divide-y divide-border/60 text-[13px]">
        <ConfigRow label="Accepting deliveries">
          <Switch
            checked={!endpoint.disabled}
            disabled={!canWrite || update.isPending}
            aria-label="Accepting deliveries"
            onCheckedChange={(on) =>
              update.mutate(
                { disabled: !on },
                {
                  onSuccess: () => toast.success(on ? "Endpoint enabled" : "Endpoint disabled"),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          />
        </ConfigRow>
        <ConfigRow label="Event types">
          <span className="text-right font-mono text-[12px]">
            {endpoint.event_types.length ? endpoint.event_types.join(", ") : "All events"}
          </span>
        </ConfigRow>
        <ConfigRow label="Rate limit">
          <span className="tabular-nums">
            {endpoint.rate_limit_per_second ? `${endpoint.rate_limit_per_second} per second` : "Unlimited"}
          </span>
        </ConfigRow>
        <ConfigRow label="Timeout">
          <span className="tabular-nums">{endpoint.timeout_seconds ? `${endpoint.timeout_seconds} s` : "Server default"}</span>
        </ConfigRow>
        {headers.length > 0 && (
          <ConfigRow label="Custom headers">
            <span className="text-right font-mono text-[12px]">
              {headers.map(([key, value]) => `${key}: ${value}`).join(", ")}
            </span>
          </ConfigRow>
        )}
        <ConfigRow label="Created">
          <span className="tabular-nums">{dateTime(endpoint.created_at)}</span>
        </ConfigRow>
      </dl>
    </Card>
  )
}

function ConfigRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-4 px-4 py-2">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  )
}

function RecentAttempts({
  appId,
  endpointId,
  onSelect,
}: {
  appId: string
  endpointId: string
  onSelect: (deliveryId: string) => void
}) {
  const attempts = useAttempts(appId, endpointId, 15)
  return (
    <Card className="gap-0 pb-0 lg:col-span-3">
      <CardHeader className="pb-3">
        <CardTitle>Recent attempts</CardTitle>
        <CardDescription>Select an attempt to see the full timeline</CardDescription>
      </CardHeader>
      {attempts.isError && !attempts.data ? (
        <QueryError error={attempts.error} onRetry={attempts.refetch} retrying={attempts.isFetching} className="py-10" />
      ) : (
      <ul className="divide-y divide-border/60 border-t border-border/60">
        {attempts.data?.data.map((attempt) => (
          <li key={attempt.id}>
            <button
              type="button"
              onClick={() => onSelect(attempt.delivery_id)}
              className="flex min-h-11 w-full items-center gap-3 px-5 text-left text-[13px] transition-colors outline-none hover:bg-accent/50 focus-visible:bg-accent/50 focus-visible:ring-4 focus-visible:ring-ring focus-visible:ring-inset"
            >
              <span className="w-16 font-mono text-[12px] text-muted-foreground tabular-nums">
                {clockTime(attempt.started_at)}
              </span>
              <HttpStatus code={attempt.status_code} error={attempt.error} />
              <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{attempt.event_type}</span>
              <span className="text-muted-foreground tabular-nums">#{attempt.attempt_number}</span>
              <span className="w-16 text-right tabular-nums">{latency(attempt.latency_ms)}</span>
            </button>
          </li>
        )) ??
          Array.from({ length: 8 }, (_, i) => (
            <li key={i} className="px-5 py-3">
              <Skeleton className="h-5 w-full" />
            </li>
          ))}
      </ul>
      )}
    </Card>
  )
}

function ReplayDeadButton({ appId, endpointId }: { appId: string; endpointId: string }) {
  const replay = useBulkReplay(appId)
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm">
          <RotateCcw /> Replay dead letters
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Replay every dead delivery?</AlertDialogTitle>
          <AlertDialogDescription>
            Each dead delivery for this endpoint is queued again with a fresh retry schedule. Receivers
            should deduplicate on the webhook-id header.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() =>
              replay.mutate(
                { endpoint_id: endpointId, status: "dead" },
                {
                  onSuccess: ({ replayed }) =>
                    toast.success(replayed ? `Replaying ${replayed} deliveries` : "No dead deliveries to replay"),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            Replay
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

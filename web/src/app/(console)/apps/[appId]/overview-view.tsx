"use client"

import { ChevronRight } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useState } from "react"
import { LatencyChart } from "@/components/charts/latency-chart"
import { VolumeChart } from "@/components/charts/volume-chart"
import { Kpi } from "@/components/kpi"
import { QueryError } from "@/components/query-error"
import { Segmented, WINDOW_OPTIONS } from "@/components/segmented"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { endpointHealth, HttpStatus, StatusDot } from "@/components/status"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { useApp, useAttempts, useEndpoints, useOverview } from "@/lib/api/hooks"
import type { StatsWindow } from "@/lib/api/schemas"
import { count, endpointName, latency, percent, timeAgo } from "@/lib/format"

const WINDOW_LABEL: Record<StatsWindow, string> = {
  "1h": "Last hour",
  "24h": "Last 24 hours",
  "7d": "Last 7 days",
}

export function OverviewView() {
  const { appId } = useParams<{ appId: string }>()
  const [range, setRange] = useState<StatsWindow>("24h")
  const app = useApp(appId)
  const overview = useOverview(appId, range)
  const stats = overview.data
  const loading = !stats

  return (
    <>
      <PageHeader title="Overview" subtitle={app.data?.name} />
      <PageBody>
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h2 className="text-[28px] leading-[34px] font-semibold tracking-tight">{app.data?.name ?? " "}</h2>
            <p className="text-[13px] text-muted-foreground">{WINDOW_LABEL[range]}</p>
          </div>
          <Segmented label="Time range" value={range} options={WINDOW_OPTIONS} onChange={setRange} />
        </div>

        {overview.isError && !stats ? (
          <Card>
            <QueryError
              error={overview.error}
              onRetry={overview.refetch}
              retrying={overview.isFetching}
              title="Couldn’t load delivery stats"
            />
          </Card>
        ) : (
          <>
        <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4" aria-label="Key metrics">
          <Kpi
            label="Messages"
            loading={loading}
            value={stats ? count(stats.messages) : null}
            hint={stats ? `${count(stats.total)} delivery attempts` : null}
          />
          <Kpi
            label="Success rate"
            loading={loading}
            value={percent(stats?.success_rate)}
            hint={stats ? `${count(stats.failed)} failed attempts` : null}
          />
          <Kpi
            label="p95 latency"
            loading={loading}
            value={latency(stats?.p95_ms)}
            hint={stats ? `p50 ${latency(stats.p50_ms)}` : null}
          />
          <Kpi
            label="Dead letters"
            loading={loading}
            tone={stats && stats.dead > 0 ? "danger" : "default"}
            value={stats ? count(stats.dead) : null}
            hint={
              stats ? (
                <Link href={`/apps/${appId}/deliveries?status=dead`} className="text-primary hover:underline">
                  Review and replay
                </Link>
              ) : null
            }
          />
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Delivery volume</CardTitle>
              <CardDescription>Attempts per interval, split by outcome</CardDescription>
            </CardHeader>
            <CardContent>
              {stats ? <VolumeChart series={stats.series} window={range} /> : <Skeleton className="h-64 w-full" />}
            </CardContent>
          </Card>
          <EndpointHealthCard appId={appId} />
        </section>

        <section className="grid gap-4 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Latency</CardTitle>
              <CardDescription>Response time of subscriber endpoints, p50 and p95</CardDescription>
            </CardHeader>
            <CardContent>
              {stats ? <LatencyChart series={stats.series} window={range} /> : <Skeleton className="h-56 w-full" />}
            </CardContent>
          </Card>
          <RecentAttempts appId={appId} />
        </section>
          </>
        )}
      </PageBody>
    </>
  )
}

function EndpointHealthCard({ appId }: { appId: string }) {
  const endpoints = useEndpoints(appId)
  return (
    <Card className="gap-0 pb-0">
      <CardHeader className="pb-3">
        <CardTitle>Endpoint health</CardTitle>
        <CardDescription>Circuit breaker state per subscriber</CardDescription>
      </CardHeader>
      {endpoints.isError && !endpoints.data ? (
        <QueryError error={endpoints.error} onRetry={endpoints.refetch} retrying={endpoints.isFetching} className="py-10" />
      ) : (
      <ul className="divide-y divide-border/60 border-t border-border/60">
        {endpoints.data
          ? endpoints.data.data.map((endpoint) => {
              const health = endpointHealth(endpoint)
              return (
                <li key={endpoint.id}>
                  <Link
                    href={`/apps/${appId}/endpoints/${endpoint.id}`}
                    className="flex min-h-12 items-center gap-3 px-5 py-2 transition-colors hover:bg-accent/50"
                  >
                    <StatusDot tone={health.tone} pulse={health.tone === "danger"} />
                    <div className="min-w-0 flex-1">
                      <div className="truncate text-[13px] font-medium">
                        {endpointName(endpoint)}
                      </div>
                      <div className="truncate text-[12px] text-muted-foreground">{health.label}</div>
                    </div>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </Link>
                </li>
              )
            })
          : Array.from({ length: 5 }, (_, i) => (
              <li key={i} className="px-5 py-3">
                <Skeleton className="h-8 w-full" />
              </li>
            ))}
      </ul>
      )}
    </Card>
  )
}

function RecentAttempts({ appId }: { appId: string }) {
  const attempts = useAttempts(appId, undefined, 8)
  return (
    <Card className="gap-0 pb-0">
      <CardHeader className="pb-3">
        <CardTitle>Recent attempts</CardTitle>
        <CardDescription>
          <Link href={`/apps/${appId}/live`} className="text-primary hover:underline">
            Open live log
          </Link>
        </CardDescription>
      </CardHeader>
      {attempts.isError && !attempts.data ? (
        <QueryError error={attempts.error} onRetry={attempts.refetch} retrying={attempts.isFetching} className="py-10" />
      ) : (
      <ul className="divide-y divide-border/60 border-t border-border/60">
        {attempts.data?.data.map((attempt) => (
          <li key={attempt.id} className="flex min-h-11 items-center gap-3 px-5 text-[13px]">
            <HttpStatus code={attempt.status_code} error={attempt.error} />
            <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{attempt.event_type}</span>
            <span className="text-[12px] text-muted-foreground tabular-nums">{timeAgo(attempt.started_at)}</span>
          </li>
        )) ??
          Array.from({ length: 6 }, (_, i) => (
            <li key={i} className="px-5 py-3">
              <Skeleton className="h-5 w-full" />
            </li>
          ))}
      </ul>
      )}
    </Card>
  )
}

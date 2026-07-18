"use client"

import { ChevronRight, Plus, Webhook } from "lucide-react"
import Link from "next/link"
import { useParams } from "next/navigation"
import { useState } from "react"
import { EmptyState } from "@/components/empty-state"
import { EndpointDialog } from "@/components/endpoint-dialog"
import { QueryError } from "@/components/query-error"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { EndpointHealthPill } from "@/components/status"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { useEndpoints, useMe } from "@/lib/api/hooks"
import { endpointName } from "@/lib/format"

export function EndpointsView() {
  const { appId } = useParams<{ appId: string }>()
  const endpoints = useEndpoints(appId)
  const me = useMe()
  const [creating, setCreating] = useState(false)
  const canWrite = me.data?.scopes.includes("endpoints:write") ?? false
  const rows = endpoints.data?.data

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setCreating(true)}>
      <Plus /> Add endpoint
    </Button>
  ) : null

  return (
    <>
      <PageHeader title="Endpoints" subtitle={rows ? `${rows.length} subscribers` : undefined} actions={addButton} />
      <PageBody>
        {endpoints.isError && !rows ? (
          <QueryError error={endpoints.error} onRetry={endpoints.refetch} retrying={endpoints.isFetching} />
        ) : rows?.length === 0 ? (
          <EmptyState
            icon={Webhook}
            title="No endpoints yet"
            description="Add the URL of a service that should receive your events. Relay signs every request so it can verify the sender."
            action={addButton}
          />
        ) : (
          <ul className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
            {rows
              ? rows.map((endpoint) => (
                  <li key={endpoint.id}>
                    <Link
                      href={`/apps/${appId}/endpoints/${endpoint.id}`}
                      className="flex min-h-16 items-center gap-4 px-5 py-3 transition-colors hover:bg-accent/50"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="truncate text-[15px] font-medium">{endpointName(endpoint)}</span>
                          <EndpointHealthPill endpoint={endpoint} />
                        </div>
                        <div className="mt-0.5 truncate font-mono text-[12px] text-muted-foreground">
                          {endpoint.url}
                        </div>
                      </div>
                      <div className="hidden shrink-0 text-right text-[12px] text-muted-foreground sm:block">
                        {endpoint.event_types.length === 0
                          ? "All events"
                          : `${endpoint.event_types.length} event type${endpoint.event_types.length === 1 ? "" : "s"}`}
                        {endpoint.rate_limit_per_second && (
                          <div className="tabular-nums">{endpoint.rate_limit_per_second}/s limit</div>
                        )}
                      </div>
                      <ChevronRight className="size-4 shrink-0 text-muted-foreground" />
                    </Link>
                  </li>
                ))
              : Array.from({ length: 5 }, (_, i) => (
                  <li key={i} className="px-5 py-4">
                    <Skeleton className="h-9 w-full" />
                  </li>
                ))}
          </ul>
        )}
      </PageBody>
      <EndpointDialog appId={appId} open={creating} onOpenChange={setCreating} />
    </>
  )
}

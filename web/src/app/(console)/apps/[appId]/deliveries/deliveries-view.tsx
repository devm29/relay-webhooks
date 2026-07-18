"use client"

import { CheckCircle2, RotateCcw } from "lucide-react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { useState } from "react"
import { toast } from "sonner"
import { DeliverySheet } from "@/components/delivery-sheet"
import { EmptyState } from "@/components/empty-state"
import { QueryError } from "@/components/query-error"
import { Segmented } from "@/components/segmented"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { RowButton } from "@/components/row-button"
import { DeliveryStatusPill, HttpStatus } from "@/components/status"
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
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/client"
import { useBulkReplay, useDeliveries, useMe, useReplayDelivery } from "@/lib/api/hooks"
import { deliveryStatus, type DeliveryStatus } from "@/lib/api/schemas"
import { hostOf, timeAgo } from "@/lib/format"

type Filter = DeliveryStatus | "all"

const FILTERS = [
  { value: "dead", label: "Dead" },
  { value: "pending", label: "Retrying" },
  { value: "succeeded", label: "Delivered" },
  { value: "all", label: "All" },
] as const satisfies readonly { value: Filter; label: string }[]

export function DeliveriesView() {
  const { appId } = useParams<{ appId: string }>()
  const params = useSearchParams()
  const router = useRouter()
  const parsed = deliveryStatus.safeParse(params.get("status"))
  const filter: Filter = params.get("status") === "all" ? "all" : parsed.success ? parsed.data : "dead"
  const [selected, setSelected] = useState<string | null>(null)
  const deliveries = useDeliveries(appId, filter === "all" ? undefined : filter)
  const replay = useReplayDelivery(appId)
  const me = useMe()
  const canReplay = me.data?.scopes.includes("deliveries:replay") ?? false
  const rows = deliveries.data?.pages.flatMap((p) => p.data)

  return (
    <>
      <PageHeader
        title="Deliveries"
        subtitle="One row per message and endpoint"
        actions={canReplay && filter === "dead" && rows && rows.length > 0 ? <ReplayAllDead appId={appId} /> : null}
      />
      <PageBody>
        <Segmented
          label="Delivery status"
          value={filter}
          options={FILTERS}
          onChange={(next) => router.replace(`/apps/${appId}/deliveries?status=${next}`)}
        />
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
          {deliveries.isError && !rows ? (
            <QueryError error={deliveries.error} onRetry={deliveries.refetch} retrying={deliveries.isFetching} />
          ) : rows?.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title={filter === "dead" ? "No dead letters" : "Nothing here"}
              description={
                filter === "dead"
                  ? "Every delivery either succeeded or is still being retried."
                  : "No deliveries match this filter yet."
              }
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[12px]">Event</TableHead>
                  <TableHead className="hidden text-[12px] md:table-cell">Endpoint</TableHead>
                  <TableHead className="text-[12px]">Status</TableHead>
                  <TableHead className="hidden text-[12px] sm:table-cell">Last response</TableHead>
                  <TableHead className="hidden text-right text-[12px] sm:table-cell">Attempts</TableHead>
                  <TableHead className="hidden text-right text-[12px] lg:table-cell">Updated</TableHead>
                  {canReplay && <TableHead className="w-24" />}
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows
                  ? rows.map((d) => (
                      <TableRow key={d.id} className="h-11 cursor-pointer hover:bg-accent/50" onClick={() => setSelected(d.id)}>
                        <TableCell>
                          <RowButton label={`Open delivery of ${d.event_type}`} onClick={() => setSelected(d.id)}>
                            {d.event_type}
                          </RowButton>
                        </TableCell>
                        <TableCell className="hidden max-w-64 truncate font-mono text-[12px] text-muted-foreground md:table-cell">
                          {hostOf(d.endpoint_url)}
                        </TableCell>
                        <TableCell>
                          <DeliveryStatusPill status={d.status} />
                        </TableCell>
                        <TableCell className="hidden sm:table-cell">
                          {d.attempt_count > 0 ? <HttpStatus code={d.last_status_code} error={d.last_error} /> : "—"}
                        </TableCell>
                        <TableCell className="hidden text-right text-[13px] tabular-nums sm:table-cell">
                          {d.attempt_count}
                        </TableCell>
                        <TableCell className="hidden text-right text-[13px] text-muted-foreground tabular-nums lg:table-cell">
                          {timeAgo(d.updated_at)}
                        </TableCell>
                        {canReplay && (
                          <TableCell className="text-right">
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label={`Replay delivery ${d.id}`}
                              disabled={replay.isPending}
                              onClick={(event) => {
                                event.stopPropagation()
                                replay.mutate(d.id, {
                                  onSuccess: () => toast.success("Queued for redelivery"),
                                  onError: (error) => toast.error(errorMessage(error)),
                                })
                              }}
                            >
                              <RotateCcw /> Replay
                            </Button>
                          </TableCell>
                        )}
                      </TableRow>
                    ))
                  : Array.from({ length: 8 }, (_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={7}>
                          <Skeleton className="h-5 w-full" />
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
          )}
        </div>
        {deliveries.hasNextPage && (
          <div className="flex justify-center">
            <Button variant="secondary" disabled={deliveries.isFetchingNextPage} onClick={() => deliveries.fetchNextPage()}>
              Load more
            </Button>
          </div>
        )}
      </PageBody>
      <DeliverySheet appId={appId} deliveryId={selected} onOpenChange={(open) => !open && setSelected(null)} />
    </>
  )
}

function ReplayAllDead({ appId }: { appId: string }) {
  const replay = useBulkReplay(appId)
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button size="sm">
          <RotateCcw /> Replay all
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Replay all dead deliveries?</AlertDialogTitle>
          <AlertDialogDescription>
            Every dead delivery in this app is queued again with a fresh retry schedule. Endpoints that are
            still disabled hold their deliveries until they are enabled.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            onClick={() =>
              replay.mutate(
                { status: "dead" },
                {
                  onSuccess: ({ replayed }) => toast.success(`Replaying ${replayed} deliveries`),
                  onError: (error) => toast.error(errorMessage(error)),
                },
              )
            }
          >
            Replay all
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

"use client"

import { RotateCcw } from "lucide-react"
import { toast } from "sonner"
import { CopyButton } from "@/components/copy-button"
import { JsonView } from "@/components/json-view"
import { QueryError } from "@/components/query-error"
import { DeliveryStatusPill, HttpStatus, StatusDot } from "@/components/status"
import { Button } from "@/components/ui/button"
import { Separator } from "@/components/ui/separator"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { errorMessage } from "@/lib/api/client"
import { useDelivery, useMe, useReplayDelivery } from "@/lib/api/hooks"
import type { Attempt, DeliveryDetail } from "@/lib/api/schemas"
import { dateTime, hostOf, latency, timeAgo } from "@/lib/format"

type Props = {
  appId: string
  deliveryId: string | null
  onOpenChange: (open: boolean) => void
}

export function DeliverySheet({ appId, deliveryId, onOpenChange }: Props) {
  const delivery = useDelivery(appId, deliveryId)
  return (
    <Sheet open={deliveryId !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-lg">
        <SheetHeader className="border-b border-border/60 p-5">
          <SheetTitle className="text-[17px]">Delivery</SheetTitle>
          <SheetDescription className="font-mono text-[12px]">{deliveryId}</SheetDescription>
        </SheetHeader>
        {delivery.isError && !delivery.data ? (
          <QueryError error={delivery.error} onRetry={delivery.refetch} retrying={delivery.isFetching} />
        ) : delivery.data ? (
          <DeliveryBody appId={appId} delivery={delivery.data} />
        ) : (
          <div className="space-y-3 p-5">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-24 w-full" />
            <Skeleton className="h-40 w-full" />
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}

function DeliveryBody({ appId, delivery }: { appId: string; delivery: DeliveryDetail }) {
  const replay = useReplayDelivery(appId)
  const me = useMe()
  const canReplay = me.data?.scopes.includes("deliveries:replay") ?? false

  return (
    <div className="space-y-6 p-5">
      <dl className="divide-y divide-border/60 rounded-xl border border-border/60 bg-card text-[13px]">
        <Row label="Status">
          <DeliveryStatusPill status={delivery.status} />
        </Row>
        <Row label="Event">
          <span className="font-mono">{delivery.event_type}</span>
        </Row>
        <Row label="Endpoint">
          <span className="truncate font-mono" title={delivery.endpoint_url}>
            {hostOf(delivery.endpoint_url)}
          </span>
        </Row>
        <Row label="Message">
          <span className="flex min-w-0 items-center gap-1 font-mono">
            <span className="truncate">{delivery.message_id}</span>
            <CopyButton value={delivery.message_id} label="Copy message id" />
          </span>
        </Row>
        {delivery.next_attempt_at && delivery.status === "pending" && (
          <Row label="Next attempt">
            <span className="tabular-nums">{timeAgo(delivery.next_attempt_at)}</span>
          </Row>
        )}
      </dl>

      {canReplay && (
        <Button
          variant="secondary"
          className="w-full"
          disabled={replay.isPending}
          onClick={() =>
            replay.mutate(delivery.id, {
              onSuccess: () => toast.success("Queued for redelivery"),
              onError: (error) => toast.error(errorMessage(error)),
            })
          }
        >
          <RotateCcw /> Replay delivery
        </Button>
      )}

      <section>
        <h3 className="mb-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Attempts
        </h3>
        {delivery.attempts.length === 0 ? (
          <p className="text-[13px] text-muted-foreground">Waiting for the first attempt.</p>
        ) : (
          <ol className="relative space-y-4">
            {delivery.attempts
              .slice()
              .reverse()
              .map((attempt, index, all) => (
                <TimelineItem key={attempt.id} attempt={attempt} last={index === all.length - 1} />
              ))}
          </ol>
        )}
      </section>

      <Separator />
      <section>
        <h3 className="mb-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
          Payload
        </h3>
        <JsonView value={delivery.payload} />
      </section>
    </div>
  )
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex min-h-11 items-center justify-between gap-4 px-4">
      <dt className="shrink-0 text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 justify-end truncate">{children}</dd>
    </div>
  )
}

function TimelineItem({ attempt, last }: { attempt: Attempt; last: boolean }) {
  const ok = attempt.outcome === "succeeded"
  return (
    <li className="relative pl-6">
      {!last && <span className="absolute top-4 bottom-[-20px] left-[3px] w-px bg-border" aria-hidden />}
      <span className="absolute top-1.5 left-0">
        <StatusDot tone={ok ? "success" : "danger"} />
      </span>
      <div className="flex items-baseline justify-between gap-3">
        <div className="text-[13px] font-medium">
          Attempt {attempt.attempt_number}
          {attempt.trigger === "replay" && (
            <span className="ml-2 text-[12px] font-normal text-primary">manual replay</span>
          )}
        </div>
        <time className="text-[12px] text-muted-foreground tabular-nums" dateTime={attempt.started_at}>
          {dateTime(attempt.started_at)}
        </time>
      </div>
      <div className="mt-1 flex items-center gap-3 text-[12px] text-muted-foreground">
        <HttpStatus code={attempt.status_code} error={attempt.error} />
        <span className="tabular-nums">{latency(attempt.latency_ms)}</span>
        {attempt.next_attempt_at && <span>retry {timeAgo(attempt.next_attempt_at)}</span>}
      </div>
      {attempt.error && attempt.status_code === null && (
        <p className="mt-1 text-[12px] text-destructive">{attempt.error}</p>
      )}
      {attempt.response_snippet && (
        <pre className="mt-2 overflow-x-auto rounded-md bg-secondary px-2.5 py-1.5 font-mono text-[11px] text-muted-foreground dark:bg-accent/40">
          {attempt.response_snippet}
        </pre>
      )}
    </li>
  )
}

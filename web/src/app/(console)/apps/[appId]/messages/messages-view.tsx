"use client"

import { Inbox, Send } from "lucide-react"
import { useParams } from "next/navigation"
import { useState } from "react"
import { CopyButton } from "@/components/copy-button"
import { DeliverySheet } from "@/components/delivery-sheet"
import { EmptyState } from "@/components/empty-state"
import { JsonView } from "@/components/json-view"
import { QueryError } from "@/components/query-error"
import { RowButton } from "@/components/row-button"
import { SendEventDialog } from "@/components/send-event-dialog"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { DeliveryStatusPill } from "@/components/status"
import { Button } from "@/components/ui/button"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { useEventTypes, useMessage, useMessages } from "@/lib/api/hooks"
import { dateTime, hostOf, timeAgo } from "@/lib/format"

export function MessagesView() {
  const { appId } = useParams<{ appId: string }>()
  const [eventType, setEventType] = useState("all")
  const [selected, setSelected] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const messages = useMessages(appId, eventType === "all" ? undefined : eventType)
  const eventTypes = useEventTypes(appId)
  const rows = messages.data?.pages.flatMap((p) => p.data)

  return (
    <>
      <PageHeader
        title="Messages"
        subtitle="Every event your backend published"
        actions={
          <Button size="sm" onClick={() => setSending(true)}>
            <Send /> Send event
          </Button>
        }
      />
      <PageBody>
        <div className="flex justify-end">
          <Select value={eventType} onValueChange={setEventType}>
            <SelectTrigger className="h-8 w-56 rounded-lg text-[13px]" aria-label="Filter by event type">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">All event types</SelectItem>
              {eventTypes.data?.map((t) => (
                <SelectItem key={t.id} value={t.name}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
          {messages.isError && !rows ? (
            <QueryError error={messages.error} onRetry={messages.refetch} retrying={messages.isFetching} />
          ) : rows?.length === 0 ? (
            <EmptyState
              icon={Inbox}
              title="No messages yet"
              description="Publish with POST /api/v1/apps/{app_id}/messages, or send a test event from here."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[12px]">Event type</TableHead>
                  <TableHead className="hidden text-[12px] md:table-cell">Message ID</TableHead>
                  <TableHead className="hidden text-[12px] lg:table-cell">Summary</TableHead>
                  <TableHead className="text-right text-[12px]">Published</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows
                  ? rows.map((m) => (
                      <TableRow key={m.id} className="h-11 cursor-pointer hover:bg-accent/50" onClick={() => setSelected(m.id)}>
                        <TableCell>
                          <RowButton label={`Open message ${m.id}`} onClick={() => setSelected(m.id)}>
                            {m.event_type}
                          </RowButton>
                        </TableCell>
                        <TableCell className="hidden font-mono text-[12px] text-muted-foreground md:table-cell">
                          {m.id}
                        </TableCell>
                        <TableCell className="hidden max-w-80 truncate font-mono text-[12px] text-muted-foreground lg:table-cell">
                          {JSON.stringify(m.payload)}
                        </TableCell>
                        <TableCell className="text-right text-[13px] text-muted-foreground tabular-nums">
                          {timeAgo(m.created_at)}
                        </TableCell>
                      </TableRow>
                    ))
                  : Array.from({ length: 8 }, (_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={4}>
                          <Skeleton className="h-5 w-full" />
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
          )}
        </div>
        {messages.hasNextPage && (
          <div className="flex justify-center">
            <Button variant="secondary" disabled={messages.isFetchingNextPage} onClick={() => messages.fetchNextPage()}>
              Load more
            </Button>
          </div>
        )}
      </PageBody>
      <MessageSheet appId={appId} messageId={selected} onClose={() => setSelected(null)} />
      <SendEventDialog appId={appId} open={sending} onOpenChange={setSending} />
    </>
  )
}

function MessageSheet({ appId, messageId, onClose }: { appId: string; messageId: string | null; onClose: () => void }) {
  const message = useMessage(appId, messageId)
  const [delivery, setDelivery] = useState<string | null>(null)
  const data = message.data
  return (
    <>
      <Sheet open={messageId !== null} onOpenChange={(open) => !open && onClose()}>
        <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-lg">
          <SheetHeader className="border-b border-border/60 p-5">
            <SheetTitle className="font-mono text-[15px]">{data?.event_type ?? "Message"}</SheetTitle>
            <SheetDescription className="flex items-center gap-1 font-mono text-[12px]">
              {messageId}
              {messageId && <CopyButton value={messageId} label="Copy message id" />}
            </SheetDescription>
          </SheetHeader>
          {message.isError && !data ? (
            <QueryError error={message.error} onRetry={message.refetch} retrying={message.isFetching} />
          ) : data ? (
            <div className="space-y-6 p-5">
              <p className="text-[13px] text-muted-foreground">Published {dateTime(data.created_at)}</p>
              <section>
                <h3 className="mb-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  Deliveries
                </h3>
                {data.deliveries.length === 0 ? (
                  <p className="text-[13px] text-muted-foreground">No endpoint was subscribed to this event type.</p>
                ) : (
                  <ul className="divide-y divide-border/60 rounded-xl border border-border/60">
                    {data.deliveries.map((d) => (
                      <li key={d.id}>
                        <button
                          type="button"
                          onClick={() => setDelivery(d.id)}
                          className="flex min-h-11 w-full items-center gap-3 px-4 text-left text-[13px] outline-none hover:bg-accent/50 focus-visible:ring-4 focus-visible:ring-ring focus-visible:ring-inset"
                        >
                          <span className="min-w-0 flex-1 truncate font-mono text-[12px]">{hostOf(d.endpoint_url)}</span>
                          <span className="text-[12px] text-muted-foreground tabular-nums">
                            {d.attempt_count} {d.attempt_count === 1 ? "attempt" : "attempts"}
                          </span>
                          <DeliveryStatusPill status={d.status} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
              <section>
                <h3 className="mb-3 text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
                  Payload
                </h3>
                <JsonView value={data.payload} />
              </section>
            </div>
          ) : (
            <div className="space-y-3 p-5">
              <Skeleton className="h-24 w-full" />
              <Skeleton className="h-40 w-full" />
            </div>
          )}
        </SheetContent>
      </Sheet>
      <DeliverySheet appId={appId} deliveryId={delivery} onOpenChange={(open) => !open && setDelivery(null)} />
    </>
  )
}

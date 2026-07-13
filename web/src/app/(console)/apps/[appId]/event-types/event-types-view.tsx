"use client"

import { Archive, ArchiveRestore, Braces, Pencil, Plus, Trash2 } from "lucide-react"
import { useParams } from "next/navigation"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { z } from "zod"
import { EmptyState } from "@/components/empty-state"
import { JsonView } from "@/components/json-view"
import { QueryError } from "@/components/query-error"
import { Segmented } from "@/components/segmented"
import { PageBody, PageHeader } from "@/components/shell/page-header"
import { StatusPill } from "@/components/status"
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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Sheet, SheetContent, SheetDescription, SheetFooter, SheetHeader, SheetTitle } from "@/components/ui/sheet"
import { Skeleton } from "@/components/ui/skeleton"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/client"
import {
  useCreateEventType,
  useDeleteEventType,
  useEventTypes,
  useMe,
  useUpdateEventType,
  type EventTypeChanges,
} from "@/lib/api/hooks"
import type { EventType } from "@/lib/api/schemas"

const SCHEMA_TEMPLATE = JSON.stringify(
  {
    type: "object",
    required: ["id"],
    properties: { id: { type: "string" } },
  },
  null,
  2,
)

type Scope = "active" | "all"

const SCOPES = [
  { value: "active", label: "Active" },
  { value: "all", label: "Including archived" },
] as const satisfies readonly { value: Scope; label: string }[]

export function EventTypesView() {
  const { appId } = useParams<{ appId: string }>()
  const [scope, setScope] = useState<Scope>("active")
  const eventTypes = useEventTypes(appId, scope === "all")
  const me = useMe()
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<EventType | null>(null)
  const [selectedName, setSelectedName] = useState<string | null>(null)
  const canWrite = me.data?.scopes.includes("event_types:write") ?? false
  const rows = eventTypes.data
  const selected = rows?.find((t) => t.name === selectedName) ?? null

  const addButton = canWrite ? (
    <Button size="sm" onClick={() => setCreating(true)}>
      <Plus /> New event type
    </Button>
  ) : null

  return (
    <>
      <PageHeader title="Event types" subtitle="The catalog your payloads are validated against" actions={addButton} />
      <PageBody>
        <Segmented label="Which event types" value={scope} options={SCOPES} onChange={setScope} />
        {eventTypes.isError && !rows ? (
          <QueryError error={eventTypes.error} onRetry={eventTypes.refetch} retrying={eventTypes.isFetching} />
        ) : rows?.length === 0 ? (
          <EmptyState
            icon={Braces}
            title="No event types yet"
            description="Register an event type and an optional JSON Schema. Messages that do not match are rejected with a precise error."
            action={addButton}
          />
        ) : (
          <ul className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
            {rows
              ? rows.map((type) => (
                  <li key={type.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedName(type.name)}
                      className="flex min-h-14 w-full items-center gap-4 px-5 py-3 text-left transition-colors outline-none hover:bg-accent/50 focus-visible:ring-4 focus-visible:ring-ring focus-visible:ring-inset"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="font-mono text-[14px] font-medium">{type.name}</div>
                        <div className="truncate text-[13px] text-muted-foreground">
                          {type.description ?? "No description"}
                        </div>
                      </div>
                      {type.archived && <StatusPill tone="neutral">Archived</StatusPill>}
                      {type.payload_schema ? (
                        <StatusPill tone="info">Schema v{type.version}</StatusPill>
                      ) : (
                        <StatusPill tone="neutral">Any payload</StatusPill>
                      )}
                    </button>
                  </li>
                ))
              : Array.from({ length: 6 }, (_, i) => (
                  <li key={i} className="px-5 py-4">
                    <Skeleton className="h-8 w-full" />
                  </li>
                ))}
          </ul>
        )}
      </PageBody>
      <EventTypeDialog
        key={editing ? `${editing.id}:${editing.version}:${editing.updated_at}` : "new"}
        appId={appId}
        existing={editing}
        open={creating || editing !== null}
        onOpenChange={(open) => {
          if (open) return
          setCreating(false)
          setEditing(null)
        }}
      />
      <Sheet open={selected !== null} onOpenChange={(open) => !open && setSelectedName(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-lg">
          <SheetHeader className="border-b border-border/60 p-5">
            <SheetTitle className="font-mono text-[15px]">{selected?.name}</SheetTitle>
            <SheetDescription>{selected?.description ?? "No description"}</SheetDescription>
          </SheetHeader>
          <div className="space-y-3 p-5">
            <h3 className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              JSON Schema (draft 2020-12){selected?.payload_schema ? `, version ${selected.version}` : ""}
            </h3>
            {selected?.payload_schema ? (
              <JsonView value={selected.payload_schema} className="max-h-none" />
            ) : (
              <p className="text-[13px] text-muted-foreground">Payloads of any shape are accepted.</p>
            )}
          </div>
          {canWrite && selected && (
            <SheetFooter className="flex-row flex-wrap gap-2 border-t border-border/60 p-5">
              <Button variant="secondary" size="sm" onClick={() => setEditing(selected)}>
                <Pencil /> Edit Schema
              </Button>
              <ArchiveButton appId={appId} eventType={selected} />
              <DeleteButton appId={appId} eventType={selected} onDeleted={() => setSelectedName(null)} />
            </SheetFooter>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}

function ArchiveButton({ appId, eventType }: { appId: string; eventType: EventType }) {
  const update = useUpdateEventType(appId)
  const archiving = !eventType.archived
  return (
    <Button
      variant="ghost"
      size="sm"
      disabled={update.isPending}
      onClick={() =>
        update.mutate(
          { name: eventType.name, changes: { archived: archiving } },
          {
            onSuccess: () => toast.success(archiving ? `${eventType.name} archived` : `${eventType.name} restored`),
            onError: (error) => toast.error(errorMessage(error)),
          },
        )
      }
    >
      {archiving ? <Archive /> : <ArchiveRestore />}
      {archiving ? "Archive" : "Restore"}
    </Button>
  )
}

function DeleteButton({ appId, eventType, onDeleted }: { appId: string; eventType: EventType; onDeleted: () => void }) {
  const remove = useDeleteEventType(appId)
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="ghost" size="sm" className="text-destructive hover:text-destructive">
          <Trash2 /> Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete {eventType.name}?</AlertDialogTitle>
          <AlertDialogDescription>
            Publishing this event type will fail until it is registered again. Messages already sent keep their
            delivery history. Archiving is the reversible alternative.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction
            className="bg-destructive text-white hover:bg-destructive/90"
            onClick={() =>
              remove.mutate(eventType.name, {
                onSuccess: () => {
                  toast.success(`${eventType.name} deleted`)
                  onDeleted()
                },
                onError: (error) => toast.error(errorMessage(error)),
              })
            }
          >
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  )
}

const schemaObject = z.record(z.string(), z.unknown())

function parseSchema(raw: string): { ok: true; value: Record<string, unknown> | null } | { ok: false } {
  if (!raw.trim()) return { ok: true, value: null }
  try {
    const parsed = schemaObject.safeParse(JSON.parse(raw))
    return parsed.success ? { ok: true, value: parsed.data } : { ok: false }
  } catch {
    return { ok: false }
  }
}

function EventTypeDialog({
  appId,
  existing,
  open,
  onOpenChange,
}: {
  appId: string
  existing: EventType | null
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const create = useCreateEventType(appId)
  const update = useUpdateEventType(appId)
  const [error, setError] = useState<string | null>(null)
  const pending = create.isPending || update.isPending

  function done(message: string) {
    toast.success(message)
    setError(null)
    onOpenChange(false)
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const schema = parseSchema(String(form.get("schema") ?? ""))
    if (!schema.ok) {
      setError("The schema must be a JSON object.")
      return
    }
    const description = String(form.get("description") ?? "").trim() || null
    const onError = (err: unknown) => setError(errorMessage(err))

    if (!existing) {
      create.mutate(
        { name: String(form.get("name") ?? "").trim(), description, payload_schema: schema.value },
        { onSuccess: (created) => done(`${created.name} registered`), onError },
      )
      return
    }

    const changes: EventTypeChanges = {}
    if (description !== existing.description) changes.description = description
    // Any schema write bumps the version, so leave it out when nothing changed.
    if (JSON.stringify(schema.value) !== JSON.stringify(existing.payload_schema)) {
      changes.payload_schema = schema.value
    }
    if (Object.keys(changes).length === 0) {
      onOpenChange(false)
      return
    }
    update.mutate(
      { name: existing.name, changes },
      {
        onSuccess: (saved) =>
          done(
            "payload_schema" in changes ? `${saved.name} is now on schema v${saved.version}` : `${saved.name} updated`,
          ),
        onError,
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>{existing ? `Edit ${existing.name}` : "New event type"}</DialogTitle>
            <DialogDescription>
              {existing
                ? "Changing the schema creates a new version. New messages are validated against it right away."
                : "Use dotted, past-tense names such as invoice.paid."}
            </DialogDescription>
          </DialogHeader>
          {!existing && (
            <div className="space-y-1.5">
              <Label htmlFor="et-name">Name</Label>
              <Input
                id="et-name"
                name="name"
                required
                pattern="^[a-zA-Z0-9_\-]+(\.[a-zA-Z0-9_\-]+)*$"
                placeholder="invoice.paid"
                className="font-mono text-[13px]"
              />
            </div>
          )}
          <div className="space-y-1.5">
            <Label htmlFor="et-description">Description</Label>
            <Input
              id="et-description"
              name="description"
              maxLength={500}
              defaultValue={existing?.description ?? ""}
              placeholder="An invoice was paid in full."
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="et-schema">JSON Schema</Label>
            <Textarea
              id="et-schema"
              name="schema"
              defaultValue={
                existing
                  ? existing.payload_schema
                    ? JSON.stringify(existing.payload_schema, null, 2)
                    : ""
                  : SCHEMA_TEMPLATE
              }
              spellCheck={false}
              className="min-h-40 font-mono text-[12px]"
            />
            <p className="text-[12px] text-muted-foreground">Leave empty to accept any payload.</p>
          </div>
          {error && (
            <p role="alert" className="text-[12px] text-destructive">
              {error}
            </p>
          )}
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {existing ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

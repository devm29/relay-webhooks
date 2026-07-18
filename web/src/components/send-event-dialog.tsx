"use client"

import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Textarea } from "@/components/ui/textarea"
import { errorMessage } from "@/lib/api/client"
import { useEventTypes, usePublishMessage } from "@/lib/api/hooks"
import { exampleFromSchema } from "@/lib/schema-example"

const payloadSchema = z.record(z.string(), z.unknown())

type Props = { appId: string; open: boolean; onOpenChange: (open: boolean) => void }

export function SendEventDialog({ appId, open, onOpenChange }: Props) {
  const eventTypes = useEventTypes(appId)
  const publish = usePublishMessage(appId)
  const [chosenType, setChosenType] = useState<string | null>(null)
  const [editedPayload, setEditedPayload] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [idempotencyKey, setIdempotencyKey] = useState(() => crypto.randomUUID())
  const renewKey = () => setIdempotencyKey(crypto.randomUUID())

  const types = eventTypes.data?.filter((t) => !t.archived) ?? []
  const eventType = chosenType ?? types[0]?.name ?? ""
  const schema = types.find((t) => t.name === eventType)?.payload_schema ?? null
  const payload = editedPayload ?? JSON.stringify(exampleFromSchema(schema), null, 2)

  function choose(name: string) {
    setChosenType(name)
    setEditedPayload(null)
    setError(null)
    renewKey()
  }

  function close(next: boolean) {
    if (!next) {
      setChosenType(null)
      setEditedPayload(null)
      setError(null)
      renewKey()
    }
    onOpenChange(next)
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    let parsed: Record<string, unknown>
    try {
      const result = payloadSchema.safeParse(JSON.parse(payload))
      if (!result.success) throw new Error("not an object")
      parsed = result.data
    } catch {
      setError("Payload must be a JSON object, for example {\"id\": 1}.")
      return
    }
    publish.mutate(
      { event_type: eventType, payload: parsed, idempotencyKey },
      {
        onSuccess: (message) => {
          toast.success(`Sent to ${message.fanout} endpoint${message.fanout === 1 ? "" : "s"}`)
          close(false)
        },
        onError: (err) => setError(errorMessage(err)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>Send test event</DialogTitle>
            <DialogDescription>
              Publishes a real message. It is validated against the event type schema and fanned out to
              every subscribed endpoint.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="send-event-type">Event type</Label>
            <Select value={eventType} onValueChange={choose}>
              <SelectTrigger id="send-event-type" className="h-9 w-full rounded-lg">
                <SelectValue placeholder="Choose an event type" />
              </SelectTrigger>
              <SelectContent>
                {types.map((t) => (
                  <SelectItem key={t.id} value={t.name}>
                    {t.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="send-payload">Payload</Label>
            <Textarea
              id="send-payload"
              value={payload}
              onChange={(e) => {
                setEditedPayload(e.target.value)
                renewKey()
              }}
              className="min-h-48 font-mono text-[12px]"
              spellCheck={false}
            />
            {error && (
              <p role="alert" className="text-[12px] text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => close(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={!eventType || publish.isPending}>
              Send event
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

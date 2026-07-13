"use client"

import { Plus, X } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
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
import { errorMessage } from "@/lib/api/client"
import { useCreateEndpoint, useEventTypes, useUpdateEndpoint, type EndpointInput } from "@/lib/api/hooks"
import type { Endpoint } from "@/lib/api/schemas"

const HEADER_NAME = /^[A-Za-z0-9-]{1,64}$/

const formSchema = z.object({
  url: z.url({ message: "Enter a full URL, including https://" }),
  name: z.string().max(120),
  description: z.string().max(500),
  secret: z.string().max(200),
  rate: z.union([z.literal(""), z.coerce.number().positive().max(1000)]),
  timeout: z.union([z.literal(""), z.coerce.number().positive().max(30)]),
})

type HeaderRow = { id: number; name: string; value: string }

let nextRowId = 0
const headerRow = (name = "", value = ""): HeaderRow => ({ id: nextRowId++, name, value })

type Props = {
  appId: string
  open: boolean
  onOpenChange: (open: boolean) => void
  endpoint?: Endpoint
}

export function EndpointDialog({ appId, open, onOpenChange, endpoint }: Props) {
  const eventTypes = useEventTypes(appId)
  const create = useCreateEndpoint(appId)
  const update = useUpdateEndpoint(appId, endpoint?.id ?? "")
  const router = useRouter()
  const [selected, setSelected] = useState<Set<string>>(new Set(endpoint?.event_types ?? []))
  const [headers, setHeaders] = useState<HeaderRow[]>(() =>
    Object.entries(endpoint?.headers ?? {}).map(([name, value]) => headerRow(name, value)),
  )
  const [error, setError] = useState<string | null>(null)
  const pending = create.isPending || update.isPending

  function toggle(name: string, on: boolean) {
    setSelected((current) => {
      const next = new Set(current)
      if (on) next.add(name)
      else next.delete(name)
      return next
    })
  }

  function setHeader(id: number, patch: Partial<Omit<HeaderRow, "id">>) {
    setHeaders((rows) => rows.map((row) => (row.id === id ? { ...row, ...patch } : row)))
  }

  function collectHeaders(): Record<string, string> | string {
    const result: Record<string, string> = {}
    for (const { name, value } of headers) {
      const key = name.trim()
      if (!key && !value.trim()) continue
      if (!HEADER_NAME.test(key)) return `"${key}" is not a valid header name. Use letters, digits and dashes.`
      result[key] = value
    }
    return result
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const parsed = formSchema.safeParse({
      url: String(form.get("url") ?? "").trim(),
      name: String(form.get("name") ?? "").trim(),
      description: String(form.get("description") ?? "").trim(),
      secret: String(form.get("secret") ?? "").trim(),
      rate: String(form.get("rate") ?? "").trim(),
      timeout: String(form.get("timeout") ?? "").trim(),
    })
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? "Check the highlighted fields.")
      return
    }
    const customHeaders = collectHeaders()
    if (typeof customHeaders === "string") {
      setError(customHeaders)
      return
    }
    const body: EndpointInput = {
      url: parsed.data.url,
      name: parsed.data.name || null,
      description: parsed.data.description || null,
      headers: customHeaders,
      event_types: [...selected],
      rate_limit_per_second: parsed.data.rate === "" ? null : parsed.data.rate,
      timeout_seconds: parsed.data.timeout === "" ? null : parsed.data.timeout,
    }
    if (!endpoint && parsed.data.secret) body.secret = parsed.data.secret
    const callbacks = {
      onError: (err: unknown) => setError(errorMessage(err)),
    }
    if (endpoint) {
      update.mutate(body, {
        ...callbacks,
        onSuccess: () => {
          toast.success("Endpoint updated")
          onOpenChange(false)
        },
      })
    } else {
      create.mutate(body, {
        ...callbacks,
        onSuccess: (created) => {
          toast.success("Endpoint added")
          onOpenChange(false)
          router.push(`/apps/${appId}/endpoints/${created.id}`)
        },
      })
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-lg">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>{endpoint ? "Edit endpoint" : "Add endpoint"}</DialogTitle>
            <DialogDescription>
              Relay POSTs signed JSON to this URL and retries with backoff until it answers 2xx.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="endpoint-url">URL</Label>
            <Input
              id="endpoint-url"
              name="url"
              type="url"
              required
              defaultValue={endpoint?.url}
              placeholder="https://api.example.com/webhooks/relay"
              className="font-mono text-[13px]"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="endpoint-name">Name</Label>
            <Input
              id="endpoint-name"
              name="name"
              maxLength={120}
              defaultValue={endpoint?.name ?? ""}
              placeholder="Ledger service"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="endpoint-description">Description</Label>
            <Input
              id="endpoint-description"
              name="description"
              defaultValue={endpoint?.description ?? ""}
              maxLength={500}
              placeholder="Books revenue when invoices are paid"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label htmlFor="endpoint-rate">Rate limit (per second)</Label>
              <Input
                id="endpoint-rate"
                name="rate"
                inputMode="decimal"
                defaultValue={endpoint?.rate_limit_per_second ?? ""}
                placeholder="Unlimited"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="endpoint-timeout">Timeout (seconds)</Label>
              <Input
                id="endpoint-timeout"
                name="timeout"
                inputMode="decimal"
                defaultValue={endpoint?.timeout_seconds ?? ""}
                placeholder="Server default"
              />
            </div>
          </div>
          <fieldset className="space-y-2">
            <legend className="text-[13px] font-medium">Event types</legend>
            <p className="text-[12px] text-muted-foreground">Leave all unchecked to receive every event.</p>
            <div className="grid max-h-44 grid-cols-1 gap-1 overflow-y-auto rounded-lg border border-border/60 p-2 sm:grid-cols-2">
              {eventTypes.data?.map((type) => (
                <label
                  key={type.id}
                  className="flex min-h-8 cursor-pointer items-center gap-2 rounded-md px-2 font-mono text-[12px] hover:bg-accent/50"
                >
                  <Checkbox
                    checked={selected.has(type.name)}
                    onCheckedChange={(state) => toggle(type.name, state === true)}
                  />
                  {type.name}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="space-y-2">
            <legend className="text-[13px] font-medium">Custom headers</legend>
            <p className="text-[12px] text-muted-foreground">
              Sent with every request, for example an auth token your receiver expects.
            </p>
            {headers.map((row) => (
              <div key={row.id} className="flex items-center gap-2">
                <Input
                  aria-label="Header name"
                  value={row.name}
                  onChange={(e) => setHeader(row.id, { name: e.target.value })}
                  placeholder="X-Team"
                  className="w-2/5 font-mono text-[12px]"
                />
                <Input
                  aria-label="Header value"
                  value={row.value}
                  onChange={(e) => setHeader(row.id, { value: e.target.value })}
                  placeholder="payments"
                  className="min-w-0 flex-1 font-mono text-[12px]"
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label={`Remove header ${row.name}`}
                  onClick={() => setHeaders((rows) => rows.filter((r) => r.id !== row.id))}
                >
                  <X />
                </Button>
              </div>
            ))}
            <Button type="button" variant="ghost" size="sm" onClick={() => setHeaders((rows) => [...rows, headerRow()])}>
              <Plus /> Add header
            </Button>
          </fieldset>
          {!endpoint && (
            <div className="space-y-1.5">
              <Label htmlFor="endpoint-secret">Signing secret</Label>
              <Input
                id="endpoint-secret"
                name="secret"
                autoComplete="off"
                spellCheck={false}
                placeholder="Generated for you"
                className="font-mono text-[12px]"
              />
              <p className="text-[12px] text-muted-foreground">
                Optional. Bring your own whsec_ secret when migrating from another provider.
              </p>
            </div>
          )}
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
              {endpoint ? "Save changes" : "Add endpoint"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

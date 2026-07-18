"use client"

import { KeyRound, Plus } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { CopyButton } from "@/components/copy-button"
import { EmptyState } from "@/components/empty-state"
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
import { QueryError } from "@/components/query-error"
import { Label } from "@/components/ui/label"
import { Skeleton } from "@/components/ui/skeleton"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { errorMessage } from "@/lib/api/client"
import { useApiKeys, useCreateApiKey, useMe, useRevokeApiKey } from "@/lib/api/hooks"
import type { ApiKey, Scope } from "@/lib/api/schemas"
import { timeAgo } from "@/lib/format"

const DEFAULT_SCOPES: Scope[] = ["messages:write", "messages:read"]

export function ApiKeysView() {
  const me = useMe()
  const allowed = me.data?.scopes.includes("api_keys:manage") ?? false
  const keys = useApiKeys(allowed)
  const [creating, setCreating] = useState(false)

  if (me.data && !allowed) {
    return (
      <>
        <PageHeader title="API keys" />
        <EmptyState
          icon={KeyRound}
          title="Admins manage API keys"
          description="Ask an owner or admin in your organization to create a key for you."
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="API keys"
        subtitle="For servers that publish events"
        actions={
          <Button size="sm" onClick={() => setCreating(true)}>
            <Plus /> New key
          </Button>
        }
      />
      <PageBody>
        <div className="overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
          {keys.isError && !keys.data ? (
            <QueryError error={keys.error} onRetry={keys.refetch} retrying={keys.isFetching} />
          ) : keys.data?.length === 0 ? (
            <EmptyState
              icon={KeyRound}
              title="No API keys"
              description="Create a key for your backend. It is shown once and stored only as a hash."
            />
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="hover:bg-transparent">
                  <TableHead className="text-[12px]">Name</TableHead>
                  <TableHead className="hidden text-[12px] md:table-cell">Scopes</TableHead>
                  <TableHead className="hidden text-[12px] sm:table-cell">Last used</TableHead>
                  <TableHead className="text-[12px]">Status</TableHead>
                  <TableHead className="w-24" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.data
                  ? keys.data.map((key) => <KeyRow key={key.id} apiKey={key} />)
                  : Array.from({ length: 3 }, (_, i) => (
                      <TableRow key={i}>
                        <TableCell colSpan={5}>
                          <Skeleton className="h-5 w-full" />
                        </TableCell>
                      </TableRow>
                    ))}
              </TableBody>
            </Table>
          )}
        </div>
      </PageBody>
      <CreateKeyDialog open={creating} onOpenChange={setCreating} grantable={me.data?.scopes ?? []} />
    </>
  )
}

function KeyRow({ apiKey }: { apiKey: ApiKey }) {
  const revoke = useRevokeApiKey()
  return (
    <TableRow className="h-12">
      <TableCell>
        <div className="text-[13px] font-medium">{apiKey.name}</div>
        <div className="font-mono text-[12px] text-muted-foreground">{apiKey.prefix}…</div>
      </TableCell>
      <TableCell className="hidden max-w-72 truncate font-mono text-[12px] text-muted-foreground md:table-cell">
        {apiKey.scopes.join(" ")}
      </TableCell>
      <TableCell className="hidden text-[13px] text-muted-foreground sm:table-cell">
        {apiKey.last_used_at ? timeAgo(apiKey.last_used_at) : "Never"}
      </TableCell>
      <TableCell>
        {apiKey.revoked_at ? <StatusPill tone="neutral">Revoked</StatusPill> : <StatusPill tone="success">Active</StatusPill>}
      </TableCell>
      <TableCell className="text-right">
        {!apiKey.revoked_at && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" size="sm">
                Revoke
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>Revoke {apiKey.name}?</AlertDialogTitle>
                <AlertDialogDescription>
                  Requests using this key start failing with 401 immediately. This cannot be undone.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-white hover:bg-destructive/90"
                  onClick={() =>
                    revoke.mutate(apiKey.id, {
                      onSuccess: () => toast.success("Key revoked"),
                      onError: (error) => toast.error(errorMessage(error)),
                    })
                  }
                >
                  Revoke key
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </TableCell>
    </TableRow>
  )
}

function CreateKeyDialog({
  open,
  onOpenChange,
  grantable,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  grantable: Scope[]
}) {
  const create = useCreateApiKey()
  const [scopes, setScopes] = useState<Set<Scope>>(new Set(DEFAULT_SCOPES))
  const [created, setCreated] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  function close(next: boolean) {
    if (!next) {
      setCreated(null)
      setError(null)
      setScopes(new Set(DEFAULT_SCOPES))
    }
    onOpenChange(next)
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim()
    create.mutate(
      { name, scopes: [...scopes] },
      {
        onSuccess: (key) => setCreated(key.key),
        onError: (err) => setError(errorMessage(err)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent className="sm:max-w-lg">
        {created ? (
          <div className="space-y-5">
            <DialogHeader>
              <DialogTitle>Copy your new key</DialogTitle>
              <DialogDescription>This is the only time it is shown. Store it in your secret manager.</DialogDescription>
            </DialogHeader>
            <div className="flex items-center gap-1 rounded-lg bg-secondary py-1 pr-1 pl-3 dark:bg-accent/40">
              <code className="min-w-0 flex-1 truncate font-mono text-[12px]">{created}</code>
              <CopyButton value={created} label="Copy key" />
            </div>
            <DialogFooter>
              <Button onClick={() => close(false)}>Done</Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={onSubmit} className="space-y-5">
            <DialogHeader>
              <DialogTitle>New API key</DialogTitle>
              <DialogDescription>Grant only what the service needs.</DialogDescription>
            </DialogHeader>
            <div className="space-y-1.5">
              <Label htmlFor="key-name">Name</Label>
              <Input id="key-name" name="name" required maxLength={120} placeholder="Billing service (production)" />
            </div>
            <fieldset className="space-y-2">
              <legend className="text-[13px] font-medium">Scopes</legend>
              <div className="grid grid-cols-1 gap-1 rounded-lg border border-border/60 p-2 sm:grid-cols-2">
                {grantable.map((scope) => (
                  <label
                    key={scope}
                    className="flex min-h-8 cursor-pointer items-center gap-2 rounded-md px-2 font-mono text-[12px] hover:bg-accent/50"
                  >
                    <Checkbox
                      checked={scopes.has(scope)}
                      onCheckedChange={(state) =>
                        setScopes((current) => {
                          const next = new Set(current)
                          if (state === true) next.add(scope)
                          else next.delete(scope)
                          return next
                        })
                      }
                    />
                    {scope}
                  </label>
                ))}
              </div>
            </fieldset>
            {error && (
              <p role="alert" className="text-[12px] text-destructive">
                {error}
              </p>
            )}
            <DialogFooter>
              <Button type="button" variant="secondary" onClick={() => close(false)}>
                Cancel
              </Button>
              <Button type="submit" disabled={create.isPending || scopes.size === 0}>
                Create key
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}

"use client"

import { useQueryClient } from "@tanstack/react-query"
import { Eye, EyeOff, RefreshCw } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"
import { CopyButton } from "@/components/copy-button"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
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
import { errorMessage } from "@/lib/api/client"
import { keys, useEndpointSecret, useFetchEndpointSecret, useRotateSecret } from "@/lib/api/hooks"
import { timeAgo } from "@/lib/format"

const OVERLAPS = [
  { value: "0", label: "Immediately" },
  { value: "3600", label: "After 1 hour" },
  { value: "86400", label: "After 24 hours" },
  { value: "604800", label: "After 7 days" },
] as const

export function SecretCard({ appId, endpointId }: { appId: string; endpointId: string }) {
  const [revealed, setRevealed] = useState(false)
  const [rotating, setRotating] = useState(false)
  const [overlap, setOverlap] = useState<string>("86400")
  const client = useQueryClient()
  const secrets = useEndpointSecret(appId, endpointId, revealed)
  const fetchSecret = useFetchEndpointSecret(appId, endpointId)
  const rotate = useRotateSecret(appId, endpointId)
  const current = secrets.data?.current.secret

  useEffect(
    () => () => client.removeQueries({ queryKey: keys.endpointSecret(appId, endpointId), exact: true }),
    [client, appId, endpointId],
  )

  return (
    <Card>
      <CardHeader>
        <CardTitle>Signing secret</CardTitle>
        <CardDescription>Verify the webhook-signature header with this secret.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center gap-1 rounded-lg bg-secondary py-1 pr-1 pl-3 dark:bg-accent/40">
          <code className="min-w-0 flex-1 truncate font-mono text-[12px]">{revealed && current ? current : `whsec_${"•".repeat(24)}`}</code>
          <Button
            variant="ghost"
            size="icon-sm"
            aria-label={revealed ? "Hide secret" : "Reveal secret"}
            onClick={() => setRevealed((r) => !r)}
          >
            {revealed ? <EyeOff /> : <Eye />}
          </Button>
          <CopyButton value={async () => (await fetchSecret()).current.secret} label="Copy secret" />
        </div>
        {revealed && secrets.isError && <p className="text-[12px] text-destructive">{errorMessage(secrets.error)}</p>}
        {revealed && secrets.data?.previous.map((old) => (
          <p key={old.id} className="text-[12px] text-muted-foreground">
            Previous secret still signs until{" "}
            {old.expires_at ? timeAgo(old.expires_at) : "revoked"}.
          </p>
        ))}
        <Button variant="secondary" size="sm" onClick={() => setRotating(true)}>
          <RefreshCw /> Rotate secret
        </Button>
      </CardContent>

      <Dialog open={rotating} onOpenChange={setRotating}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Rotate signing secret</DialogTitle>
            <DialogDescription>
              During the overlap Relay signs with both secrets, so receivers can deploy the new one
              without dropping a single webhook.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="overlap">Retire the current secret</Label>
            <Select value={overlap} onValueChange={setOverlap}>
              <SelectTrigger id="overlap" className="h-9 w-full rounded-lg">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {OVERLAPS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button variant="secondary" onClick={() => setRotating(false)}>
              Cancel
            </Button>
            <Button
              disabled={rotate.isPending}
              onClick={() =>
                rotate.mutate(
                  { overlap_seconds: Number(overlap) },
                  {
                    onSuccess: () => {
                      setRotating(false)
                      setRevealed(true)
                      toast.success("New secret is live")
                    },
                    onError: (error) => toast.error(errorMessage(error)),
                  },
                )
              }
            >
              Rotate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

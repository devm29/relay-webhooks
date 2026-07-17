"use client"

import { Plus } from "lucide-react"
import { useRouter } from "next/navigation"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { errorMessage } from "@/lib/api/client"
import { useCreateApp } from "@/lib/api/hooks"

export function NewAppButton({ variant = "default" }: { variant?: "default" | "ghost" }) {
  const [open, setOpen] = useState(false)
  const create = useCreateApp()
  const router = useRouter()

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const description = String(form.get("description") ?? "").trim()
    create.mutate(
      { name: String(form.get("name") ?? "").trim(), description: description || null },
      {
        onSuccess: (app) => {
          setOpen(false)
          toast.success(`${app.name} is ready`)
          router.push(`/apps/${app.id}`)
        },
        onError: (error) => toast.error(errorMessage(error)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        {variant === "ghost" ? (
          <Button variant="ghost" size="icon-xs" aria-label="New app" className="text-muted-foreground">
            <Plus />
          </Button>
        ) : (
          <Button>
            <Plus /> New app
          </Button>
        )}
      </DialogTrigger>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>New app</DialogTitle>
            <DialogDescription>Apps keep endpoints, event types and history separate.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="app-name">Name</Label>
            <Input id="app-name" name="name" required maxLength={120} placeholder="Storefront (staging)" />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="app-description">Description</Label>
            <Input id="app-description" name="description" maxLength={500} placeholder="Optional" />
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              Create app
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

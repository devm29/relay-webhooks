"use client"

import { Plus } from "lucide-react"
import { useState, type FormEvent } from "react"
import { toast } from "sonner"
import { QueryError } from "@/components/query-error"
import { PageBody, PageHeader } from "@/components/shell/page-header"
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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Skeleton } from "@/components/ui/skeleton"
import { errorMessage } from "@/lib/api/client"
import { useCreateMember, useMe, useMembers, useUpdateMemberRole } from "@/lib/api/hooks"
import { role as roleSchema, type Role, type User } from "@/lib/api/schemas"

const ROLE_COPY: Record<Role, string> = {
  owner: "Everything, including transferring ownership",
  admin: "Manage members, API keys and apps",
  developer: "Endpoints, event types, publishing and replay",
  viewer: "Read-only access to delivery data",
}

const RANK: Record<Role, number> = { viewer: 0, developer: 1, admin: 2, owner: 3 }

function assignable(actor: Role | undefined): Role[] {
  if (!actor) return []
  return roleSchema.options.filter((r) => actor === "owner" || RANK[r] < RANK[actor])
}

export function MembersView() {
  const me = useMe()
  const members = useMembers()
  const [adding, setAdding] = useState(false)
  const canManage = me.data?.scopes.includes("members:manage") ?? false
  const actorRole = me.data?.user?.role

  return (
    <>
      <PageHeader
        title="Members"
        subtitle={me.data?.org.name}
        actions={
          canManage ? (
            <Button size="sm" onClick={() => setAdding(true)}>
              <Plus /> Add member
            </Button>
          ) : null
        }
      />
      <PageBody>
        {members.isError && !members.data ? (
          <div className="rounded-xl border border-border/60 bg-card shadow-xs">
            <QueryError error={members.error} onRetry={members.refetch} retrying={members.isFetching} />
          </div>
        ) : (
        <ul className="divide-y divide-border/60 overflow-hidden rounded-xl border border-border/60 bg-card shadow-xs">
          {members.data
            ? members.data.map((member) => (
                <MemberRow
                  key={member.id}
                  member={member}
                  isSelf={member.id === me.data?.user?.id}
                  options={canManage ? assignable(actorRole) : []}
                />
              ))
            : Array.from({ length: 4 }, (_, i) => (
                <li key={i} className="px-5 py-4">
                  <Skeleton className="h-8 w-full" />
                </li>
              ))}
        </ul>
        )}
        <section className="grid gap-3 sm:grid-cols-2">
          {roleSchema.options.map((r) => (
            <div key={r} className="rounded-xl border border-border/60 bg-card p-4 shadow-xs">
              <div className="text-[13px] font-semibold capitalize">{r}</div>
              <div className="text-[13px] text-muted-foreground">{ROLE_COPY[r]}</div>
            </div>
          ))}
        </section>
      </PageBody>
      <AddMemberDialog open={adding} onOpenChange={setAdding} roles={assignable(actorRole)} />
    </>
  )
}

function MemberRow({ member, isSelf, options }: { member: User; isSelf: boolean; options: Role[] }) {
  const update = useUpdateMemberRole()
  const editable = !isSelf && options.includes(member.role)
  return (
    <li className="flex min-h-14 items-center gap-4 px-5 py-2">
      <span className="flex size-9 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] font-semibold">
        {member.name
          .split(" ")
          .map((p) => p[0] ?? "")
          .join("")
          .slice(0, 2)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[14px] font-medium">
          {member.name}
          {isSelf && <span className="ml-2 text-[12px] font-normal text-muted-foreground">You</span>}
        </div>
        <div className="truncate text-[13px] text-muted-foreground">{member.email}</div>
      </div>
      {editable ? (
        <Select
          value={member.role}
          onValueChange={(value) => {
            const next = roleSchema.safeParse(value)
            if (!next.success) return
            update.mutate(
              { userId: member.id, role: next.data },
              {
                onSuccess: () => toast.success(`${member.name} is now ${next.data}`),
                onError: (error) => toast.error(errorMessage(error)),
              },
            )
          }}
        >
          <SelectTrigger className="h-8 w-32 rounded-lg text-[13px] capitalize" aria-label={`Role for ${member.name}`}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {options.map((r) => (
              <SelectItem key={r} value={r} className="capitalize">
                {r}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      ) : (
        <span className="text-[13px] text-muted-foreground capitalize">{member.role}</span>
      )}
    </li>
  )
}

function AddMemberDialog({
  open,
  onOpenChange,
  roles,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  roles: Role[]
}) {
  const create = useCreateMember()
  const [role, setRole] = useState<Role>("developer")
  const [error, setError] = useState<string | null>(null)

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    create.mutate(
      {
        name: String(form.get("name") ?? "").trim(),
        email: String(form.get("email") ?? "").trim(),
        password: String(form.get("password") ?? ""),
        role,
      },
      {
        onSuccess: (user) => {
          toast.success(`${user.name} added`)
          setError(null)
          onOpenChange(false)
        },
        onError: (err) => setError(errorMessage(err)),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit} className="space-y-5">
          <DialogHeader>
            <DialogTitle>Add member</DialogTitle>
            <DialogDescription>Share the temporary password with them directly.</DialogDescription>
          </DialogHeader>
          <div className="space-y-1.5">
            <Label htmlFor="member-name">Name</Label>
            <Input id="member-name" name="name" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="member-email">Email</Label>
            <Input id="member-email" name="email" type="email" required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="member-password">Temporary password</Label>
            <Input id="member-password" name="password" type="password" minLength={10} required />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="member-role">Role</Label>
            <Select
              value={role}
              onValueChange={(value) => {
                const next = roleSchema.safeParse(value)
                if (next.success) setRole(next.data)
              }}
            >
              <SelectTrigger id="member-role" className="h-9 w-full rounded-lg capitalize">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {roles.map((r) => (
                  <SelectItem key={r} value={r} className="capitalize">
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
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
            <Button type="submit" disabled={create.isPending}>
              Add member
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

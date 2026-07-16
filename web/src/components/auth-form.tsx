"use client"

import { Loader2 } from "lucide-react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useState, type FormEvent } from "react"
import { z } from "zod"
import { LogoMark } from "@/components/logo"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { errorMessage, request } from "@/lib/api/client"
import { safeNext } from "@/lib/safe-next"

type Mode = "login" | "signup"

const okSchema = z.object({ ok: z.literal(true) })

const DEMO = process.env.NEXT_PUBLIC_DEMO_MODE === "true"

const COPY: Record<Mode, { title: string; subtitle: string; action: string }> = {
  login: {
    title: "Sign in to Relay",
    subtitle: "Webhook delivery you can see.",
    action: "Sign in",
  },
  signup: {
    title: "Create your workspace",
    subtitle: "You will be the owner of a new organization.",
    action: "Create account",
  },
}

export function AuthForm({ mode }: { mode: Mode }) {
  const router = useRouter()
  const params = useSearchParams()
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const copy = COPY[mode]

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const form = new FormData(event.currentTarget)
    const field = (name: string) => String(form.get(name) ?? "")
    setPending(true)
    setError(null)
    try {
      if (mode === "login") {
        await request("/api/session", okSchema, {
          method: "POST",
          body: { email: field("email"), password: field("password") },
        })
      } else {
        await request("/api/session/signup", okSchema, {
          method: "POST",
          body: {
            org_name: field("org_name"),
            name: field("name"),
            email: field("email"),
            password: field("password"),
          },
        })
      }
      router.replace(safeNext(params.get("next")))
      router.refresh()
    } catch (err) {
      setError(errorMessage(err))
      setPending(false)
    }
  }

  return (
    <div className="rounded-2xl border border-border/60 bg-card p-8 shadow-sm">
      <div className="mb-8 flex flex-col items-center text-center">
        <LogoMark className="mb-5 size-11" />
        <h1 className="text-[22px] leading-7 font-semibold tracking-tight">{copy.title}</h1>
        <p className="mt-1 text-[13px] text-muted-foreground">{copy.subtitle}</p>
      </div>
      <form className="space-y-4" onSubmit={onSubmit} noValidate={false}>
        {mode === "signup" && (
          <>
            <Field label="Organization" name="org_name" autoComplete="organization" />
            <Field label="Your name" name="name" autoComplete="name" />
          </>
        )}
        <Field
          label="Email"
          name="email"
          type="email"
          autoComplete="email"
          defaultValue={DEMO && mode === "login" ? "demo@relay.dev" : undefined}
        />
        <Field
          label="Password"
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={mode === "signup" ? 10 : undefined}
          defaultValue={DEMO && mode === "login" ? "relay-demo-password" : undefined}
        />
        {error && (
          <p role="alert" className="text-[12px] text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={pending}>
          {pending && <Loader2 className="animate-spin" />}
          {copy.action}
        </Button>
      </form>
      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        {mode === "login" ? (
          <>
            New to Relay?{" "}
            <Link href="/signup" className="text-primary hover:underline">
              Create an account
            </Link>
          </>
        ) : (
          <>
            Already have an account?{" "}
            <Link href="/login" className="text-primary hover:underline">
              Sign in
            </Link>
          </>
        )}
      </p>
    </div>
  )
}

type FieldProps = {
  label: string
  name: string
  type?: string
  autoComplete?: string
  defaultValue?: string | undefined
  minLength?: number | undefined
}

function Field({ label, name, type = "text", autoComplete, defaultValue, minLength }: FieldProps) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name} className="text-[13px] font-medium">
        {label}
      </Label>
      <Input
        id={name}
        name={name}
        type={type}
        required
        autoComplete={autoComplete}
        defaultValue={defaultValue}
        minLength={minLength}
      />
    </div>
  )
}

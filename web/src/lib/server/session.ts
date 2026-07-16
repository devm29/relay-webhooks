import "server-only"
import { cookies } from "next/headers"
import { z } from "zod"
import { API_URL, SECURE_COOKIES, SESSION_COOKIE } from "./config"

const tokenSchema = z.object({
  access_token: z.string().min(1),
  expires_at: z.string(),
})

const errorSchema = z.object({
  error: z.object({ code: z.string(), message: z.string(), details: z.unknown().optional() }),
})

export type SessionResult =
  | { ok: true }
  | { ok: false; status: number; body: z.infer<typeof errorSchema> }

export async function exchangeForSession(path: "/auth/login" | "/auth/signup", body: unknown): Promise<SessionResult> {
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  })
  const json: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = errorSchema.safeParse(json)
    return {
      ok: false,
      status: response.status,
      body: parsed.success
        ? parsed.data
        : { error: { code: "upstream_error", message: "Relay API is unavailable. Try again shortly." } },
    }
  }
  const token = tokenSchema.parse(json)
  const store = await cookies()
  store.set(SESSION_COOKIE, token.access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: SECURE_COOKIES,
    path: "/",
    expires: new Date(token.expires_at),
  })
  return { ok: true }
}

export async function readSessionToken(): Promise<string | undefined> {
  const store = await cookies()
  return store.get(SESSION_COOKIE)?.value
}

export async function clearSession(): Promise<void> {
  const store = await cookies()
  store.delete(SESSION_COOKIE)
}

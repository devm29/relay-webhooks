import "server-only"
import { redirect } from "next/navigation"
import type { z } from "zod"
import { API_URL } from "./config"
import { readSessionToken } from "./session"

/**
 * Server-component fetch against the API. A missing or rejected session goes through the
 * logout route so the stale cookie is cleared; otherwise middleware would send the visitor
 * straight back here. Any other failure throws and lands on the nearest error boundary.
 */
export async function serverRelay<T extends z.ZodType>(path: string, schema: T): Promise<z.infer<T>> {
  const token = await readSessionToken()
  if (!token) redirect("/api/session/logout")
  const response = await fetch(`${API_URL}/api/v1${path}`, {
    headers: { authorization: `Bearer ${token}` },
    cache: "no-store",
  })
  if (response.status === 401) redirect("/api/session/logout")
  if (!response.ok) throw new Error(`Relay API responded ${response.status} for ${path}`)
  return schema.parse(await response.json())
}

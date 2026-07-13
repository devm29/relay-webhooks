import { z } from "zod"

const claims = z.object({ exp: z.number() })

function decodeSegment(segment: string): unknown {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/")
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4)
  return JSON.parse(atob(padded))
}

/**
 * Reads the exp claim without verifying the signature. That is enough to stop routing a
 * visitor with a dead cookie into the console; the API still verifies every request.
 */
export function sessionIsCurrent(token: string | undefined, nowMs = Date.now()): boolean {
  const payload = token?.split(".")[1]
  if (!payload) return false
  try {
    const parsed = claims.safeParse(decodeSegment(payload))
    return parsed.success && parsed.data.exp * 1000 > nowMs
  } catch {
    return false
  }
}

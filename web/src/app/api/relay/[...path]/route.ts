import { NextResponse, type NextRequest } from "next/server"
import { API_URL, SESSION_COOKIE } from "@/lib/server/config"
import { readSessionToken } from "@/lib/server/session"

export const dynamic = "force-dynamic"

const FORWARDED_REQUEST_HEADERS = ["content-type", "idempotency-key", "accept", "last-event-id"]
const FORWARDED_RESPONSE_HEADERS = ["content-type", "cache-control", "idempotent-replayed", "x-request-id"]

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params
  const token = await readSessionToken()
  if (!token) {
    return Response.json(
      { error: { code: "unauthenticated", message: "Your session has ended. Sign in again." } },
      { status: 401 },
    )
  }

  const headers = new Headers({ authorization: `Bearer ${token}` })
  for (const name of FORWARDED_REQUEST_HEADERS) {
    const value = request.headers.get(name)
    if (value) headers.set(name, value)
  }

  const target = `${API_URL}/api/v1/${path.map(encodeURIComponent).join("/")}${request.nextUrl.search}`
  const hasBody = request.method !== "GET" && request.method !== "HEAD"
  const upstream = await fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : null,
    cache: "no-store",
    signal: request.signal,
  })

  const responseHeaders = new Headers()
  for (const name of FORWARDED_RESPONSE_HEADERS) {
    const value = upstream.headers.get(name)
    if (value) responseHeaders.set(name, value)
  }
  if (upstream.headers.get("content-type")?.includes("text/event-stream")) {
    responseHeaders.set("cache-control", "no-cache, no-transform")
    responseHeaders.set("x-accel-buffering", "no")
  }
  const response = new NextResponse(upstream.body, { status: upstream.status, headers: responseHeaders })
  // A rejected token is dead for good (expired, revoked user, rotated secret); drop it so
  // middleware stops treating the browser as signed in.
  if (upstream.status === 401) response.cookies.delete(SESSION_COOKIE)
  return response
}

export { proxy as GET, proxy as POST, proxy as PATCH, proxy as PUT, proxy as DELETE }

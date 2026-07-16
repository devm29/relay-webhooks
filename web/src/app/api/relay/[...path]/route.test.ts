import { NextRequest } from "next/server"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const session = vi.hoisted(() => ({ token: undefined as string | undefined }))
vi.mock("@/lib/server/session", () => ({ readSessionToken: async () => session.token }))

const { GET, POST } = await import("./route")

const fetchMock = vi.fn<typeof fetch>()

function call(handler: typeof GET, path: string[], init?: { method?: string; body?: string; headers?: Record<string, string> }) {
  const url = new URL(`/api/relay/${path.join("/")}?limit=5`, "http://localhost:3108")
  const request = new NextRequest(url, init)
  return handler(request, { params: Promise.resolve({ path }) })
}

beforeEach(() => {
  session.token = "token-123"
  vi.stubGlobal("fetch", fetchMock)
})

afterEach(() => {
  fetchMock.mockReset()
  vi.unstubAllGlobals()
})

describe("relay proxy", () => {
  it("rejects requests without a session before reaching the API", async () => {
    session.token = undefined
    const response = await call(GET, ["apps"])
    expect(response.status).toBe(401)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it("forwards the bearer token, the query and whitelisted headers only", async () => {
    fetchMock.mockResolvedValue(Response.json({ data: [] }, { headers: { "x-request-id": "req_1", "set-cookie": "a=b" } }))
    const response = await call(POST, ["apps", "app 1", "messages"], {
      method: "POST",
      body: '{"event_type":"ping"}',
      headers: { "content-type": "application/json", "idempotency-key": "k1", cookie: "relay_session=x" },
    })

    const [target, init] = fetchMock.mock.calls[0] ?? []
    expect(String(target)).toBe("http://127.0.0.1:8108/api/v1/apps/app%201/messages?limit=5")
    const headers = new Headers(init?.headers)
    expect(headers.get("authorization")).toBe("Bearer token-123")
    expect(headers.get("idempotency-key")).toBe("k1")
    expect(headers.get("cookie")).toBeNull()
    expect(init?.body).toBe('{"event_type":"ping"}')

    expect(response.status).toBe(200)
    expect(response.headers.get("x-request-id")).toBe("req_1")
    expect(response.headers.get("set-cookie")).toBeNull()
  })

  it("clears the session cookie when the API rejects the token", async () => {
    fetchMock.mockResolvedValue(
      Response.json({ error: { code: "unauthenticated", message: "expired" } }, { status: 401 }),
    )
    const response = await call(GET, ["apps"])
    expect(response.status).toBe(401)
    expect(response.headers.get("set-cookie")).toMatch(/relay_session=;/)
  })
})

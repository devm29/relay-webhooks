import { NextRequest } from "next/server"
import { describe, expect, it, vi } from "vitest"

vi.mock("@/lib/server/session", () => ({
  exchangeForSession: vi.fn(async () => ({ ok: true })),
  clearSession: vi.fn(async () => undefined),
}))

const { POST: login } = await import("./route")
const { GET: logout } = await import("./logout/route")

describe("session routes", () => {
  it("answers 400 rather than 500 for a body that is not JSON", async () => {
    const response = await login(new Request("http://localhost/api/session", { method: "POST", body: "{oops" }))
    expect(response.status).toBe(400)
    expect(await response.json()).toMatchObject({ error: { code: "invalid_body" } })
  })

  it("logout clears the cookie and keeps only a same-origin next", () => {
    const local = logout(new NextRequest("http://localhost/api/session/logout?next=/apps/app_1"))
    expect(local.status).toBe(307)
    expect(local.headers.get("location")).toBe("/login?next=%2Fapps%2Fapp_1")
    expect(local.headers.get("set-cookie")).toMatch(/relay_session=;/)

    const hostile = logout(new NextRequest("http://localhost/api/session/logout?next=//evil.example"))
    expect(hostile.headers.get("location")).toBe("/login")
  })
})

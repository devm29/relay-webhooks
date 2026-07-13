import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

const jar = vi.hoisted(() => ({ set: vi.fn(), get: vi.fn(), delete: vi.fn() }))
vi.mock("next/headers", () => ({ cookies: async () => jar }))

const { exchangeForSession } = await import("./session")

const fetchMock = vi.fn<typeof fetch>()

beforeEach(() => vi.stubGlobal("fetch", fetchMock))

afterEach(() => {
  fetchMock.mockReset()
  jar.set.mockReset()
  vi.unstubAllGlobals()
})

describe("exchangeForSession", () => {
  it("stores the issued token in an httpOnly cookie", async () => {
    fetchMock.mockResolvedValue(Response.json({ access_token: "jwt-abc", expires_at: "2030-01-01T00:00:00Z" }))
    expect(await exchangeForSession("/auth/login", { email: "a@b.c" })).toEqual({ ok: true })
    expect(jar.set).toHaveBeenCalledWith("relay_session", "jwt-abc", expect.objectContaining({ httpOnly: true }))
  })

  it("passes the API's own error envelope through", async () => {
    const envelope = { error: { code: "invalid_credentials", message: "Wrong email or password" } }
    fetchMock.mockResolvedValue(Response.json(envelope, { status: 401 }))
    expect(await exchangeForSession("/auth/login", {})).toEqual({ ok: false, status: 401, body: envelope })
  })

  it("reports an unreachable API instead of throwing", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"))
    const result = await exchangeForSession("/auth/login", {})
    expect(result).toMatchObject({ ok: false, status: 502, body: { error: { code: "upstream_error" } } })
    expect(jar.set).not.toHaveBeenCalled()
  })
})

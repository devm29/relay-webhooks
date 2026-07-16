import { describe, expect, it } from "vitest"
import { fakeJwt } from "@/test/jwt"
import { sessionIsCurrent } from "./session-token"

const NOW = Date.UTC(2026, 2, 1, 12)

describe("sessionIsCurrent", () => {
  it("accepts a token that has not expired", () => {
    expect(sessionIsCurrent(fakeJwt({ exp: NOW / 1000 + 60, sub: "usr_1" }), NOW)).toBe(true)
  })

  it("rejects expired, malformed and missing tokens", () => {
    expect(sessionIsCurrent(fakeJwt({ exp: NOW / 1000 - 1 }), NOW)).toBe(false)
    expect(sessionIsCurrent(fakeJwt({ sub: "usr_1" }), NOW)).toBe(false)
    expect(sessionIsCurrent("not-a-jwt", NOW)).toBe(false)
    expect(sessionIsCurrent("a.%%%.c", NOW)).toBe(false)
    expect(sessionIsCurrent(undefined, NOW)).toBe(false)
  })
})

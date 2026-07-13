import { describe, expect, it } from "vitest"
import { safeNext } from "./safe-next"

describe("safeNext", () => {
  it("keeps same-origin paths with their query", () => {
    expect(safeNext("/apps/app_1/deliveries?status=dead")).toBe("/apps/app_1/deliveries?status=dead")
  })

  it.each([
    "//evil.example",
    "/\\evil.example",
    "/\t/evil.example",
    "https://evil.example",
    "javascript:alert(1)",
    "apps",
    "",
  ])("falls back for %j", (next) => {
    expect(safeNext(next)).toBe("/")
  })

  it("falls back when missing", () => {
    expect(safeNext(null)).toBe("/")
    expect(safeNext(undefined, "/home")).toBe("/home")
  })
})

import { describe, expect, it } from "vitest"
import { hostOf, latency, percent, timeAgo } from "./format"

describe("format", () => {
  it("renders latency in ms or seconds", () => {
    expect(latency(42.4)).toBe("42 ms")
    expect(latency(1530)).toBe("1.5 s")
    expect(latency(15_000)).toBe("15 s")
    expect(latency(null)).toBe("—")
  })

  it("renders ratios as percentages", () => {
    expect(percent(0.9876)).toBe("98.8%")
    expect(percent(1, 0)).toBe("100%")
    expect(percent(undefined)).toBe("—")
  })

  it("describes relative time in both directions", () => {
    const now = Date.parse("2026-03-01T12:00:00Z")
    expect(timeAgo("2026-03-01T11:58:00Z", now)).toBe("2 minutes ago")
    expect(timeAgo("2026-03-01T12:00:30Z", now)).toBe("in 30 seconds")
    expect(timeAgo("2026-03-01T12:00:02Z", now)).toBe("just now")
  })

  it("strips scheme and query from endpoint URLs", () => {
    expect(hostOf("https://hooks.example.com/relay?x=1")).toBe("hooks.example.com/relay")
    expect(hostOf("not a url")).toBe("not a url")
  })
})

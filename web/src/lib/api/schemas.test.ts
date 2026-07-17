import { describe, expect, it } from "vitest"
import { endpoint, liveEvent, page } from "./schemas"

describe("API schemas", () => {
  it("parses an endpoint page from the backend", () => {
    const parsed = page(endpoint).parse({
      data: [
        {
          id: "ep_1",
          app_id: "app_1",
          name: null,
          url: "https://hooks.example.com",
          description: null,
          event_types: [],
          rate_limit_per_second: 5,
          timeout_seconds: null,
          headers: { "x-team": "billing" },
          disabled: false,
          disabled_reason: null,
          created_at: "2026-03-01T12:00:00Z",
          updated_at: "2026-03-01T12:00:00Z",
          breaker: { state: "open", consecutive_failures: 5, trip_count: 1, opened_at: null, open_until: null },
        },
      ],
      next_cursor: null,
    })
    expect(parsed.data[0]?.breaker?.state).toBe("open")
  })

  it("rejects live events with unknown kinds", () => {
    const base = {
      app_id: "app_1",
      id: "atm_1",
      message_id: "msg_1",
      event_type: "invoice.paid",
      endpoint_id: null,
      delivery_id: null,
      outcome: null,
      status_code: null,
      latency_ms: null,
      attempt_number: null,
      delivery_status: null,
      at: "2026-03-01T12:00:00Z",
    }
    expect(liveEvent.safeParse({ ...base, kind: "message" }).success).toBe(true)
    expect(liveEvent.safeParse({ ...base, kind: "bogus" }).success).toBe(false)
  })
})

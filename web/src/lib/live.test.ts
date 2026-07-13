import { describe, expect, it } from "vitest"
import { parseLiveEvent } from "./live"

const attempt = {
  kind: "attempt",
  app_id: "app_1",
  id: "atm_1",
  message_id: "msg_1",
  event_type: "invoice.paid",
  endpoint_id: "ep_1",
  delivery_id: "dlv_1",
  outcome: "failed",
  status_code: 503,
  latency_ms: 120,
  attempt_number: 2,
  delivery_status: "pending",
  at: "2026-03-01T12:00:00Z",
}

describe("parseLiveEvent", () => {
  it("parses a well-formed frame", () => {
    expect(parseLiveEvent(JSON.stringify(attempt))?.status_code).toBe(503)
  })

  it("drops malformed JSON and frames that do not match the schema", () => {
    expect(parseLiveEvent("{not json")).toBeNull()
    expect(parseLiveEvent(JSON.stringify({ ...attempt, kind: "other" }))).toBeNull()
    expect(parseLiveEvent("")).toBeNull()
  })
})

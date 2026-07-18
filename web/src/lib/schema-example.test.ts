import { describe, expect, it } from "vitest"
import { exampleFromSchema } from "./schema-example"

describe("exampleFromSchema", () => {
  it("fills every property with a value of the declared type", () => {
    const example = exampleFromSchema({
      type: "object",
      properties: {
        invoice_id: { type: "string" },
        amount: { type: "integer", minimum: 0 },
        currency: { type: "string", enum: ["usd", "eur"] },
        lines: { type: "array", items: { type: "object", properties: { qty: { type: "integer", minimum: 1 } } } },
        paid: { type: "boolean" },
      },
    })
    expect(example).toEqual({
      invoice_id: "inv_8f2a91c4d7",
      amount: 4900,
      currency: "usd",
      lines: [{ qty: 1 }],
      paid: true,
    })
  })

  it("falls back gracefully for missing or non-object schemas", () => {
    expect(exampleFromSchema(null)).toEqual({ hello: "world" })
    expect(exampleFromSchema({ type: "string" })).toEqual({})
  })
})

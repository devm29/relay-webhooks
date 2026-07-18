import { z } from "zod"

const node: z.ZodType<SchemaNode> = z.lazy(() =>
  z
    .object({
      type: z.union([z.string(), z.array(z.string())]).optional(),
      enum: z.array(z.unknown()).optional(),
      properties: z.record(z.string(), node).optional(),
      items: node.optional(),
      minimum: z.number().optional(),
    })
    .passthrough(),
)

type SchemaNode = {
  type?: string | string[] | undefined
  enum?: unknown[] | undefined
  properties?: Record<string, SchemaNode> | undefined
  items?: SchemaNode | undefined
  minimum?: number | undefined
}

function sample(schema: SchemaNode, key: string): unknown {
  if (schema.enum?.length) return schema.enum[0]
  const type = Array.isArray(schema.type) ? schema.type[0] : schema.type
  switch (type) {
    case "object":
      return Object.fromEntries(
        Object.entries(schema.properties ?? {}).map(([name, child]) => [name, sample(child, name)]),
      )
    case "array":
      return schema.items ? [sample(schema.items, key)] : []
    case "integer":
    case "number":
      return Math.max(schema.minimum ?? 0, key.includes("amount") ? 4900 : 1)
    case "boolean":
      return true
    case "string":
      if (key.endsWith("_id")) return `${key.replace(/_id$/, "").slice(0, 3)}_8f2a91c4d7`
      if (key.includes("email")) return "taylor@example.com"
      return key
    default:
      return null
  }
}

/** Builds a plausible payload from a JSON Schema so test events validate on the first try. */
export function exampleFromSchema(schema: Record<string, unknown> | null): Record<string, unknown> {
  if (!schema) return { hello: "world" }
  const parsed = node.safeParse(schema)
  if (!parsed.success) return {}
  const value = z.record(z.string(), z.unknown()).safeParse(sample(parsed.data, ""))
  return value.success ? value.data : {}
}

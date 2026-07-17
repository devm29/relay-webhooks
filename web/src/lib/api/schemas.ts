import { z } from "zod"

export const deliveryStatus = z.enum(["pending", "succeeded", "dead"])
export const breakerState = z.enum(["closed", "open", "half_open"])
export const role = z.enum(["owner", "admin", "developer", "viewer"])
export const statsWindow = z.enum(["1h", "24h", "7d"])

export const scopes = [
  "apps:read",
  "apps:write",
  "endpoints:read",
  "endpoints:write",
  "event_types:read",
  "event_types:write",
  "messages:read",
  "messages:write",
  "deliveries:replay",
  "api_keys:manage",
  "members:manage",
] as const
export const scope = z.enum(scopes)

const timestamp = z.string()

export const page = <T extends z.ZodType>(item: T) =>
  z.object({ data: z.array(item), next_cursor: z.string().nullable() })

export const apiErrorBody = z.object({
  error: z.object({
    code: z.string(),
    message: z.string(),
    details: z.array(z.object({ path: z.string(), message: z.string() })).nullable().optional(),
  }),
})

export const org = z.object({ id: z.string(), name: z.string(), created_at: timestamp })

export const user = z.object({
  id: z.string(),
  org_id: z.string(),
  email: z.string(),
  name: z.string(),
  role,
  created_at: timestamp,
})

export const me = z.object({
  user: user.nullable(),
  org,
  scopes: z.array(scope),
  principal: z.enum(["user", "api_key"]),
})

export const app = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  created_at: timestamp,
})

export const breaker = z.object({
  state: breakerState,
  consecutive_failures: z.number(),
  trip_count: z.number(),
  opened_at: timestamp.nullable(),
  open_until: timestamp.nullable(),
})

export const endpoint = z.object({
  id: z.string(),
  app_id: z.string(),
  name: z.string().nullable(),
  url: z.string(),
  description: z.string().nullable(),
  event_types: z.array(z.string()),
  rate_limit_per_second: z.number().nullable(),
  timeout_seconds: z.number().nullable(),
  headers: z.record(z.string(), z.string()),
  disabled: z.boolean(),
  disabled_reason: z.string().nullable(),
  created_at: timestamp,
  updated_at: timestamp,
  breaker: breaker.nullable(),
})

export const secret = z.object({
  id: z.string(),
  secret: z.string(),
  created_at: timestamp,
  expires_at: timestamp.nullable(),
})

export const endpointSecrets = z.object({ current: secret, previous: z.array(secret) })

export const jsonObject = z.record(z.string(), z.unknown())

export const eventType = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string().nullable(),
  payload_schema: jsonObject.nullable(),
  version: z.number(),
  archived: z.boolean(),
  created_at: timestamp,
  updated_at: timestamp,
})

export const message = z.object({
  id: z.string(),
  app_id: z.string(),
  event_type: z.string(),
  event_id: z.string().nullable(),
  payload: jsonObject,
  created_at: timestamp,
})

export const messageCreated = message.extend({ fanout: z.number(), idempotent_replay: z.boolean() })

export const delivery = z.object({
  id: z.string(),
  app_id: z.string(),
  message_id: z.string(),
  endpoint_id: z.string(),
  status: deliveryStatus,
  attempt_count: z.number(),
  next_attempt_at: timestamp.nullable(),
  last_status_code: z.number().nullable(),
  last_error: z.string().nullable(),
  delivered_at: timestamp.nullable(),
  created_at: timestamp,
  updated_at: timestamp,
  event_type: z.string(),
  endpoint_url: z.string(),
})

export const attempt = z.object({
  id: z.string(),
  delivery_id: z.string(),
  message_id: z.string(),
  endpoint_id: z.string(),
  attempt_number: z.number(),
  trigger: z.enum(["scheduled", "replay"]),
  outcome: z.enum(["succeeded", "failed"]),
  status_code: z.number().nullable(),
  error: z.string().nullable(),
  response_snippet: z.string().nullable(),
  latency_ms: z.number(),
  started_at: timestamp,
  next_attempt_at: timestamp.nullable(),
})

export const attemptLog = attempt.extend({
  event_type: z.string(),
  endpoint_url: z.string(),
  delivery_status: deliveryStatus,
})

export const deliveryDetail = delivery.extend({ payload: jsonObject, attempts: z.array(attempt) })
export const messageDetail = message.extend({ deliveries: z.array(delivery) })

export const statsBucket = z.object({
  ts: timestamp,
  total: z.number(),
  succeeded: z.number(),
  failed: z.number(),
  p50_ms: z.number().nullable(),
  p95_ms: z.number().nullable(),
})

export const latencyStats = z.object({
  window: statsWindow,
  total: z.number(),
  succeeded: z.number(),
  failed: z.number(),
  success_rate: z.number().nullable(),
  p50_ms: z.number().nullable(),
  p95_ms: z.number().nullable(),
  series: z.array(statsBucket),
})

export const overview = latencyStats.extend({
  messages: z.number(),
  pending: z.number(),
  dead: z.number(),
  endpoints: z.object({
    total: z.number(),
    healthy: z.number(),
    degraded: z.number(),
    open: z.number(),
    disabled: z.number(),
  }),
})

export const apiKey = z.object({
  id: z.string(),
  name: z.string(),
  prefix: z.string(),
  scopes: z.array(scope),
  created_at: timestamp,
  expires_at: timestamp.nullable(),
  last_used_at: timestamp.nullable(),
  revoked_at: timestamp.nullable(),
})

export const apiKeyCreated = apiKey.extend({ key: z.string() })
export const replayResult = z.object({ replayed: z.number() })

export const liveEvent = z.object({
  kind: z.enum(["attempt", "message"]),
  app_id: z.string(),
  id: z.string(),
  message_id: z.string(),
  event_type: z.string(),
  endpoint_id: z.string().nullable(),
  delivery_id: z.string().nullable(),
  outcome: z.enum(["succeeded", "failed"]).nullable(),
  status_code: z.number().nullable(),
  latency_ms: z.number().nullable(),
  attempt_number: z.number().nullable(),
  delivery_status: deliveryStatus.nullable(),
  at: timestamp,
})

export type DeliveryStatus = z.infer<typeof deliveryStatus>
export type BreakerState = z.infer<typeof breakerState>
export type Role = z.infer<typeof role>
export type Scope = z.infer<typeof scope>
export type StatsWindow = z.infer<typeof statsWindow>
export type Me = z.infer<typeof me>
export type App = z.infer<typeof app>
export type Endpoint = z.infer<typeof endpoint>
export type EndpointSecrets = z.infer<typeof endpointSecrets>
export type EventType = z.infer<typeof eventType>
export type Message = z.infer<typeof message>
export type MessageDetail = z.infer<typeof messageDetail>
export type Delivery = z.infer<typeof delivery>
export type DeliveryDetail = z.infer<typeof deliveryDetail>
export type Attempt = z.infer<typeof attempt>
export type AttemptLog = z.infer<typeof attemptLog>
export type LatencyStats = z.infer<typeof latencyStats>
export type StatsBucket = z.infer<typeof statsBucket>
export type Overview = z.infer<typeof overview>
export type ApiKey = z.infer<typeof apiKey>
export type ApiKeyCreated = z.infer<typeof apiKeyCreated>
export type User = z.infer<typeof user>
export type LiveEvent = z.infer<typeof liveEvent>
export type Page<T> = { data: T[]; next_cursor: string | null }

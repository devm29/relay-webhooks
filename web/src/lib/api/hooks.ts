"use client"

import {
  keepPreviousData,
  queryOptions,
  useInfiniteQuery,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query"
import { z } from "zod"
import { query, relay } from "./client"
import * as s from "./schemas"
import type { DeliveryStatus, Role, Scope, StatsWindow } from "./schemas"

export const keys = {
  me: ["me"] as const,
  apps: ["apps"] as const,
  app: (appId: string) => ["apps", appId] as const,
  overview: (appId: string, window: StatsWindow) => ["apps", appId, "overview", window] as const,
  endpoints: (appId: string) => ["apps", appId, "endpoints"] as const,
  endpoint: (appId: string, id: string) => ["apps", appId, "endpoints", id] as const,
  endpointStats: (appId: string, id: string, window: StatsWindow) =>
    ["apps", appId, "endpoints", id, "stats", window] as const,
  endpointSecret: (appId: string, id: string) => ["apps", appId, "endpoints", id, "secret"] as const,
  attempts: (appId: string, endpointId?: string) => ["apps", appId, "attempts", endpointId ?? "all"] as const,
  messages: (appId: string, eventType?: string) => ["apps", appId, "messages", eventType ?? "all"] as const,
  message: (appId: string, id: string) => ["apps", appId, "message", id] as const,
  deliveries: (appId: string, status?: DeliveryStatus) =>
    ["apps", appId, "deliveries", status ?? "all"] as const,
  delivery: (appId: string, id: string) => ["apps", appId, "delivery", id] as const,
  eventTypes: (appId: string) => ["apps", appId, "event-types"] as const,
  apiKeys: ["api-keys"] as const,
  members: ["members"] as const,
}

export function useMe() {
  return useQuery({ queryKey: keys.me, queryFn: () => relay("/auth/me", s.me), staleTime: 60_000 })
}

export function useApps() {
  return useQuery({
    queryKey: keys.apps,
    queryFn: () => relay(`/apps${query({ limit: 200 })}`, s.page(s.app)),
    staleTime: 60_000,
  })
}

export function useApp(appId: string) {
  return useQuery({ queryKey: keys.app(appId), queryFn: () => relay(`/apps/${appId}`, s.app) })
}

export function useOverview(appId: string, window: StatsWindow) {
  return useQuery({
    queryKey: keys.overview(appId, window),
    queryFn: () => relay(`/apps/${appId}/stats${query({ window })}`, s.overview),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })
}

export function useEndpoints(appId: string) {
  return useQuery({
    queryKey: keys.endpoints(appId),
    queryFn: () => relay(`/apps/${appId}/endpoints${query({ limit: 200 })}`, s.page(s.endpoint)),
    refetchInterval: 15_000,
  })
}

export function useEndpoint(appId: string, endpointId: string) {
  return useQuery({
    queryKey: keys.endpoint(appId, endpointId),
    queryFn: () => relay(`/apps/${appId}/endpoints/${endpointId}`, s.endpoint),
    refetchInterval: 10_000,
  })
}

export function useEndpointStats(appId: string, endpointId: string, window: StatsWindow) {
  return useQuery({
    queryKey: keys.endpointStats(appId, endpointId, window),
    queryFn: () =>
      relay(`/apps/${appId}/endpoints/${endpointId}/stats${query({ window })}`, s.latencyStats),
    placeholderData: keepPreviousData,
    refetchInterval: 15_000,
  })
}

// Plaintext secrets are fetched only on demand and dropped from the cache as soon as
// nothing on screen uses them.
function endpointSecretQuery(appId: string, endpointId: string) {
  return queryOptions({
    queryKey: keys.endpointSecret(appId, endpointId),
    queryFn: () => relay(`/apps/${appId}/endpoints/${endpointId}/secret`, s.endpointSecrets),
    gcTime: 0,
    staleTime: 30_000,
  })
}

export function useEndpointSecret(appId: string, endpointId: string, enabled: boolean) {
  return useQuery({ ...endpointSecretQuery(appId, endpointId), enabled })
}

export function useFetchEndpointSecret(appId: string, endpointId: string) {
  const client = useQueryClient()
  return () => client.fetchQuery(endpointSecretQuery(appId, endpointId))
}

export function useAttempts(appId: string, endpointId?: string, limit = 50) {
  return useQuery({
    queryKey: keys.attempts(appId, endpointId),
    queryFn: () =>
      relay(
        `/apps/${appId}/attempts${query({ endpoint_id: endpointId, limit })}`,
        s.page(s.attemptLog),
      ),
  })
}

export function useMessages(appId: string, eventType?: string) {
  return useInfiniteQuery({
    queryKey: keys.messages(appId, eventType),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      relay(
        `/apps/${appId}/messages${query({ event_type: eventType, before: pageParam, limit: 50 })}`,
        s.page(s.message),
      ),
    getNextPageParam: (last) => last.next_cursor,
  })
}

export function useMessage(appId: string, messageId: string | null) {
  return useQuery({
    queryKey: keys.message(appId, messageId ?? ""),
    queryFn: () => relay(`/apps/${appId}/messages/${messageId ?? ""}`, s.messageDetail),
    enabled: messageId !== null,
  })
}

export function useDeliveries(appId: string, status?: DeliveryStatus) {
  return useInfiniteQuery({
    queryKey: keys.deliveries(appId, status),
    initialPageParam: null as string | null,
    queryFn: ({ pageParam }) =>
      relay(
        `/apps/${appId}/deliveries${query({ status, before: pageParam, limit: 50 })}`,
        s.page(s.delivery),
      ),
    getNextPageParam: (last) => last.next_cursor,
  })
}

export function useDelivery(appId: string, deliveryId: string | null) {
  return useQuery({
    queryKey: keys.delivery(appId, deliveryId ?? ""),
    queryFn: () => relay(`/apps/${appId}/deliveries/${deliveryId ?? ""}`, s.deliveryDetail),
    enabled: deliveryId !== null,
  })
}

export function useEventTypes(appId: string, includeArchived = false) {
  return useQuery({
    queryKey: [...keys.eventTypes(appId), includeArchived ? "with-archived" : "active"],
    queryFn: () =>
      relay(`/apps/${appId}/event-types${query({ include_archived: includeArchived ? "true" : null })}`, z.array(s.eventType)),
    staleTime: 60_000,
  })
}

export function useApiKeys(enabled: boolean) {
  return useQuery({
    queryKey: keys.apiKeys,
    queryFn: () => relay("/api-keys", z.array(s.apiKey)),
    enabled,
  })
}

export function useMembers() {
  return useQuery({ queryKey: keys.members, queryFn: () => relay("/members", z.array(s.user)) })
}

function useInvalidateApp(appId: string) {
  const client = useQueryClient()
  return () => client.invalidateQueries({ queryKey: keys.app(appId) })
}

export type EndpointInput = {
  url: string
  name?: string | null
  description?: string | null
  headers?: Record<string, string>
  secret?: string
  event_types?: string[]
  rate_limit_per_second?: number | null
  timeout_seconds?: number | null
  disabled?: boolean
}

export function useCreateEndpoint(appId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: (body: EndpointInput) =>
      relay(`/apps/${appId}/endpoints`, s.endpoint, { method: "POST", body }),
    onSuccess: invalidate,
  })
}

export function useUpdateEndpoint(appId: string, endpointId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: (body: Partial<EndpointInput>) =>
      relay(`/apps/${appId}/endpoints/${endpointId}`, s.endpoint, { method: "PATCH", body }),
    onSuccess: invalidate,
  })
}

export function useEnableEndpoint(appId: string, endpointId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: () =>
      relay(`/apps/${appId}/endpoints/${endpointId}/enable`, s.endpoint, { method: "POST" }),
    onSuccess: invalidate,
  })
}

export function useRotateSecret(appId: string, endpointId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { overlap_seconds: number }) =>
      relay(`/apps/${appId}/endpoints/${endpointId}/secret/rotate`, s.endpointSecrets, {
        method: "POST",
        body,
      }),
    onSuccess: (data) => client.setQueryData(keys.endpointSecret(appId, endpointId), data),
  })
}

export function useReplayDelivery(appId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: (deliveryId: string) =>
      relay(`/apps/${appId}/deliveries/${deliveryId}/replay`, s.delivery, { method: "POST" }),
    onSuccess: invalidate,
  })
}

export function useBulkReplay(appId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: (body: { endpoint_id?: string; status: "dead" | "succeeded" }) =>
      relay(`/apps/${appId}/deliveries/replay`, s.replayResult, { method: "POST", body }),
    onSuccess: invalidate,
  })
}

export type PublishInput = {
  event_type: string
  payload: Record<string, unknown>
  // Callers keep one key per logical send so a retry after a lost response is deduplicated.
  idempotencyKey: string
}

export function usePublishMessage(appId: string) {
  const invalidate = useInvalidateApp(appId)
  return useMutation({
    mutationFn: ({ idempotencyKey, ...body }: PublishInput) =>
      relay(`/apps/${appId}/messages`, s.messageCreated, {
        method: "POST",
        body,
        headers: { "idempotency-key": idempotencyKey },
      }),
    onSuccess: invalidate,
  })
}

export function useCreateEventType(appId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: {
      name: string
      description: string | null
      payload_schema: Record<string, unknown> | null
    }) => relay(`/apps/${appId}/event-types`, s.eventType, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.eventTypes(appId) }),
  })
}

export type EventTypeChanges = {
  description?: string | null
  payload_schema?: Record<string, unknown> | null
  archived?: boolean
}

export function useUpdateEventType(appId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ name, changes }: { name: string; changes: EventTypeChanges }) =>
      relay(`/apps/${appId}/event-types/${encodeURIComponent(name)}`, s.eventType, {
        method: "PATCH",
        body: changes,
      }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.eventTypes(appId) }),
  })
}

export function useDeleteEventType(appId: string) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) =>
      relay(`/apps/${appId}/event-types/${encodeURIComponent(name)}`, z.undefined(), { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.eventTypes(appId) }),
  })
}

export function useCreateApp() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; description: string | null }) =>
      relay("/apps", s.app, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.apps }),
  })
}

export function useCreateApiKey() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; scopes: Scope[] }) =>
      relay("/api-keys", s.apiKeyCreated, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.apiKeys }),
  })
}

export function useRevokeApiKey() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (keyId: string) => relay(`/api-keys/${keyId}`, s.apiKey, { method: "DELETE" }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.apiKeys }),
  })
}

export function useCreateMember() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; email: string; password: string; role: Role }) =>
      relay("/members", s.user, { method: "POST", body }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.members }),
  })
}

export function useUpdateMemberRole() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: Role }) =>
      relay(`/members/${userId}`, s.user, { method: "PATCH", body: { role } }),
    onSuccess: () => client.invalidateQueries({ queryKey: keys.members }),
  })
}

export function useSignOut() {
  return useMutation({
    mutationFn: async () => {
      await fetch("/api/session", { method: "DELETE" })
    },
    onSuccess: () => window.location.assign("/login"),
  })
}

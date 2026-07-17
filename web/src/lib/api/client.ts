import { z } from "zod"
import { apiErrorBody } from "./schemas"

export type FieldError = { path: string; message: string }

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
    readonly details: FieldError[] = [],
  ) {
    super(message)
    this.name = "ApiError"
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE"
  body?: unknown
  headers?: Record<string, string>
  signal?: AbortSignal
}

export async function request<T extends z.ZodType>(
  url: string,
  schema: T,
  options: RequestOptions = {},
): Promise<z.infer<T>> {
  const headers: Record<string, string> = { accept: "application/json", ...options.headers }
  const init: RequestInit = { method: options.method ?? "GET", headers, cache: "no-store" }
  if (options.body !== undefined) {
    headers["content-type"] = "application/json"
    init.body = JSON.stringify(options.body)
  }
  if (options.signal) init.signal = options.signal

  const response = await fetch(url, init)
  if (response.status === 401 && typeof window !== "undefined" && !url.startsWith("/api/session")) {
    // The proxy has already cleared the dead cookie, so middleware will let /login through.
    const here = `${window.location.pathname}${window.location.search}`
    window.location.assign(`/login?next=${encodeURIComponent(here)}`)
  }
  if (response.status === 204) return schema.parse(undefined)

  const json: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const parsed = apiErrorBody.safeParse(json)
    if (parsed.success) {
      const { code, message, details } = parsed.data.error
      throw new ApiError(response.status, code, message, details ?? [])
    }
    throw new ApiError(response.status, "unknown", "Something went wrong. Try again in a moment.")
  }
  return schema.parse(json)
}

export function relay<T extends z.ZodType>(path: string, schema: T, options?: RequestOptions) {
  return request(`/api/relay${path}`, schema, options)
}

export function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ""
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    const first = error.details[0]
    return first ? `${error.message}: ${first.path} ${first.message}` : error.message
  }
  return "Something went wrong. Try again in a moment."
}

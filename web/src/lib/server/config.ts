import "server-only"
import { z } from "zod"

const env = z
  .object({
    RELAY_API_URL: z.url().default("http://127.0.0.1:8108"),
    NODE_ENV: z.enum(["development", "production", "test"]).default("development"),
    // Plain-http deployments (the local compose stack) must turn this off, or Safari drops the cookie.
    RELAY_SECURE_COOKIES: z.enum(["true", "false"]).optional(),
  })
  .parse(process.env)

export { SESSION_COOKIE } from "@/lib/session-cookie"
export const API_URL = env.RELAY_API_URL.replace(/\/$/, "")
export const SECURE_COOKIES =
  env.RELAY_SECURE_COOKIES === undefined ? env.NODE_ENV === "production" : env.RELAY_SECURE_COOKIES === "true"

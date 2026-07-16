import { NextRequest } from "next/server"
import { describe, expect, it } from "vitest"
import { expiredJwt, liveJwt } from "@/test/jwt"
import { middleware } from "./middleware"

function visit(path: string, token?: string) {
  const headers = new Headers(token ? { cookie: `relay_session=${token}` } : {})
  return middleware(new NextRequest(new URL(path, "http://localhost:3108"), { headers }))
}

const location = (response: Response) => response.headers.get("location")

describe("middleware", () => {
  it("sends signed-out visitors to login and remembers where they were going", () => {
    const response = visit("/apps/app_1/deliveries?status=dead")
    expect(response.status).toBe(307)
    const target = new URL(location(response) ?? "")
    expect(target.pathname).toBe("/login")
    expect(target.searchParams.get("next")).toBe("/apps/app_1/deliveries?status=dead")
  })

  it("lets a current session into the console and bounces it off the login page", () => {
    expect(location(visit("/apps/app_1", liveJwt()))).toBeNull()
    expect(new URL(location(visit("/login", liveJwt())) ?? "").pathname).toBe("/")
  })

  it("treats an expired cookie as signed out and clears it, so there is no redirect loop", () => {
    const fromConsole = visit("/", expiredJwt())
    expect(new URL(location(fromConsole) ?? "").pathname).toBe("/login")
    expect(fromConsole.headers.get("set-cookie")).toMatch(/relay_session=;/)

    const onLogin = visit("/login", expiredJwt())
    expect(location(onLogin)).toBeNull()
    expect(onLogin.headers.get("set-cookie")).toMatch(/relay_session=;/)
  })

  it("does not treat lookalike paths as public", () => {
    expect(new URL(location(visit("/loginx")) ?? "").pathname).toBe("/login")
  })
})

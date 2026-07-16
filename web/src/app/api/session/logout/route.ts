import { NextResponse, type NextRequest } from "next/server"
import { SESSION_COOKIE } from "@/lib/server/config"
import { safeNext } from "@/lib/safe-next"

export const dynamic = "force-dynamic"

export function GET(request: NextRequest) {
  const next = safeNext(request.nextUrl.searchParams.get("next"), "/")
  const login = next === "/" ? "/login" : `/login?${new URLSearchParams({ next })}`
  // A relative Location keeps the browser on whichever host it used; behind `next start`
  // request.url reports the bind hostname, which may not be the one holding the cookie.
  const response = new NextResponse(null, { status: 307, headers: { location: login } })
  response.cookies.delete(SESSION_COOKIE)
  return response
}

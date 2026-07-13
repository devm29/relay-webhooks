import { NextResponse, type NextRequest } from "next/server"
import { SESSION_COOKIE } from "@/lib/session-cookie"
import { sessionIsCurrent } from "@/lib/session-token"

const PUBLIC_PATHS = ["/login", "/signup"]

export function middleware(request: NextRequest) {
  const { pathname, search } = request.nextUrl
  const cookie = request.cookies.get(SESSION_COOKIE)?.value
  const signedIn = sessionIsCurrent(cookie)
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))

  let response: NextResponse
  if (!signedIn && !isPublic) {
    const url = new URL("/login", request.url)
    if (pathname !== "/") url.searchParams.set("next", `${pathname}${search}`)
    response = NextResponse.redirect(url)
  } else if (signedIn && isPublic) {
    response = NextResponse.redirect(new URL("/", request.url))
  } else {
    response = NextResponse.next()
  }
  if (cookie !== undefined && !signedIn) response.cookies.delete(SESSION_COOKIE)
  return response
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico|icon.svg).*)"],
}

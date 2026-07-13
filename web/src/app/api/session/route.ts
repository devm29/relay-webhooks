import { NextResponse } from "next/server"
import { clearSession, exchangeForSession } from "@/lib/server/session"
import { readJson } from "@/lib/server/read-json"

export async function POST(request: Request) {
  const input = await readJson(request)
  if (!input.ok) return input.response
  const result = await exchangeForSession("/auth/login", input.body)
  if (!result.ok) return NextResponse.json(result.body, { status: result.status })
  return NextResponse.json({ ok: true })
}

export async function DELETE() {
  await clearSession()
  return new NextResponse(null, { status: 204 })
}

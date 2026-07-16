import { NextResponse } from "next/server"
import { exchangeForSession } from "@/lib/server/session"
import { readJson } from "@/lib/server/read-json"

export async function POST(request: Request) {
  const input = await readJson(request)
  if (!input.ok) return input.response
  const result = await exchangeForSession("/auth/signup", input.body)
  if (!result.ok) return NextResponse.json(result.body, { status: result.status })
  return NextResponse.json({ ok: true }, { status: 201 })
}

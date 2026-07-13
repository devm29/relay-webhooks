import "server-only"
import { NextResponse } from "next/server"

export async function readJson(request: Request): Promise<{ ok: true; body: unknown } | { ok: false; response: NextResponse }> {
  const body: unknown = await request.json().catch(() => undefined)
  if (body === undefined || body === null || typeof body !== "object") {
    return {
      ok: false,
      response: NextResponse.json(
        { error: { code: "invalid_body", message: "Expected a JSON object in the request body." } },
        { status: 400 },
      ),
    }
  }
  return { ok: true, body }
}

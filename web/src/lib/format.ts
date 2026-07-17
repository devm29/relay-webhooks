const relative = new Intl.RelativeTimeFormat("en", { numeric: "auto" })
const UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86_400_000],
  ["hour", 3_600_000],
  ["minute", 60_000],
  ["second", 1_000],
]

export function timeAgo(iso: string, now: number = Date.now()): string {
  const diff = new Date(iso).getTime() - now
  for (const [unit, ms] of UNITS) {
    if (Math.abs(diff) >= ms || unit === "second") {
      const value = Math.round(diff / ms)
      if (unit === "second" && Math.abs(value) < 5) return "just now"
      return relative.format(value, unit)
    }
  }
  return "just now"
}

const timeFormat = new Intl.DateTimeFormat("en", {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})
const dateTimeFormat = new Intl.DateTimeFormat("en", {
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
})

export const clockTime = (iso: string) => timeFormat.format(new Date(iso))
export const dateTime = (iso: string) => dateTimeFormat.format(new Date(iso))

export function latency(ms: number | null | undefined): string {
  if (ms === null || ms === undefined) return "—"
  return ms >= 1000 ? `${(ms / 1000).toFixed(ms >= 10_000 ? 0 : 1)} s` : `${Math.round(ms)} ms`
}

export function percent(ratio: number | null | undefined, digits = 1): string {
  if (ratio === null || ratio === undefined) return "—"
  return `${(ratio * 100).toFixed(digits)}%`
}

const compact = new Intl.NumberFormat("en", { notation: "compact", maximumFractionDigits: 1 })
export const count = (value: number) => compact.format(value)

export function hostOf(url: string): string {
  try {
    const parsed = new URL(url)
    return `${parsed.host}${parsed.pathname}`
  } catch {
    return url
  }
}

export function endpointName(endpoint: { name: string | null; url: string }): string {
  return endpoint.name?.trim() || hostOf(endpoint.url)
}

import type { StatsWindow } from "@/lib/api/schemas"

const hourMinute = new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", hour12: false })
const dayHour = new Intl.DateTimeFormat("en", { weekday: "short", hour: "2-digit", hour12: false })

export function tickFormatter(window: StatsWindow) {
  return (value: string) => (window === "7d" ? dayHour : hourMinute).format(new Date(value))
}

export function tooltipLabel(value: unknown): string {
  return typeof value === "string" ? new Date(value).toLocaleString() : ""
}

export const AXIS_PROPS = {
  tickLine: false,
  axisLine: false,
  tickMargin: 8,
  fontSize: 11,
} as const

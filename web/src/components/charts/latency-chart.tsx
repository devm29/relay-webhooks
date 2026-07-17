"use client"

import { CartesianGrid, Line, LineChart, XAxis, YAxis } from "recharts"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import type { StatsBucket, StatsWindow } from "@/lib/api/schemas"
import { latency } from "@/lib/format"
import { AXIS_PROPS, tickFormatter, tooltipLabel } from "./axis"

const config = {
  p50_ms: { label: "p50", color: "var(--chart-1)" },
  p95_ms: { label: "p95", color: "var(--chart-4)" },
} satisfies ChartConfig

export function LatencyChart({ series, window }: { series: StatsBucket[]; window: StatsWindow }) {
  return (
    <ChartContainer config={config} className="aspect-auto h-56 w-full">
      <LineChart data={series} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="ts" {...AXIS_PROPS} minTickGap={40} tickFormatter={tickFormatter(window)} />
        <YAxis {...AXIS_PROPS} width={52} tickFormatter={(v: number) => latency(v)} />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={tooltipLabel}
              formatter={(value, name) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">{name === "p50_ms" ? "p50" : "p95"}</span>
                  <span className="font-medium tabular-nums">{latency(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        {(["p50_ms", "p95_ms"] as const).map((key) => (
          <Line
            key={key}
            dataKey={key}
            type="monotone"
            stroke={`var(--color-${key})`}
            strokeWidth={2}
            dot={false}
            connectNulls
            isAnimationActive={false}
          />
        ))}
        <ChartLegend content={<ChartLegendContent />} />
      </LineChart>
    </ChartContainer>
  )
}

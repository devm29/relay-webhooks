"use client"

import { Area, AreaChart, CartesianGrid, XAxis, YAxis } from "recharts"
import {
  ChartContainer,
  ChartLegend,
  ChartLegendContent,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import type { StatsBucket, StatsWindow } from "@/lib/api/schemas"
import { count } from "@/lib/format"
import { AXIS_PROPS, tickFormatter, tooltipLabel } from "./axis"

const config = {
  succeeded: { label: "Delivered", color: "var(--chart-1)" },
  failed: { label: "Failed", color: "var(--destructive)" },
} satisfies ChartConfig

export function VolumeChart({ series, window }: { series: StatsBucket[]; window: StatsWindow }) {
  return (
    <ChartContainer config={config} className="aspect-auto h-64 w-full">
      <AreaChart data={series} margin={{ left: 0, right: 8, top: 8 }}>
        <defs>
          {(["succeeded", "failed"] as const).map((key) => (
            <linearGradient key={key} id={`fill-${key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={`var(--color-${key})`} stopOpacity={0.2} />
              <stop offset="100%" stopColor={`var(--color-${key})`} stopOpacity={0} />
            </linearGradient>
          ))}
        </defs>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="ts" {...AXIS_PROPS} minTickGap={40} tickFormatter={tickFormatter(window)} />
        <YAxis {...AXIS_PROPS} width={40} allowDecimals={false} tickFormatter={count} />
        <ChartTooltip content={<ChartTooltipContent labelFormatter={tooltipLabel} />} />
        <Area
          dataKey="succeeded"
          type="monotone"
          stackId="a"
          stroke="var(--color-succeeded)"
          strokeWidth={2}
          fill="url(#fill-succeeded)"
          isAnimationActive={false}
        />
        <Area
          dataKey="failed"
          type="monotone"
          stackId="a"
          stroke="var(--color-failed)"
          strokeWidth={2}
          fill="url(#fill-failed)"
          isAnimationActive={false}
        />
        <ChartLegend content={<ChartLegendContent />} />
      </AreaChart>
    </ChartContainer>
  )
}

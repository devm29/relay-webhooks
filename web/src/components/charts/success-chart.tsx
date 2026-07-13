"use client"

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import type { StatsBucket, StatsWindow } from "@/lib/api/schemas"
import { percent } from "@/lib/format"
import { AXIS_PROPS, tickFormatter, tooltipLabel } from "./axis"

const config = { rate: { label: "Success rate", color: "var(--chart-5)" } } satisfies ChartConfig

export function SuccessChart({ series, window }: { series: StatsBucket[]; window: StatsWindow }) {
  const data = series.map((bucket) => ({
    ts: bucket.ts,
    rate: bucket.total ? bucket.succeeded / bucket.total : null,
  }))
  return (
    <ChartContainer config={config} className="aspect-auto h-56 w-full">
      <BarChart data={data} margin={{ left: 0, right: 8, top: 8 }}>
        <CartesianGrid vertical={false} strokeDasharray="3 3" className="stroke-border" />
        <XAxis dataKey="ts" {...AXIS_PROPS} minTickGap={40} tickFormatter={tickFormatter(window)} />
        <YAxis
          {...AXIS_PROPS}
          width={44}
          domain={[0, 1]}
          ticks={[0, 0.5, 1]}
          tickFormatter={(v: number) => percent(v, 0)}
        />
        <ChartTooltip
          content={
            <ChartTooltipContent
              labelFormatter={tooltipLabel}
              formatter={(value) => (
                <div className="flex w-full justify-between gap-4">
                  <span className="text-muted-foreground">Success rate</span>
                  <span className="font-medium tabular-nums">{percent(Number(value))}</span>
                </div>
              )}
            />
          }
        />
        <Bar dataKey="rate" fill="var(--color-rate)" radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ChartContainer>
  )
}

"use client"

import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs"

type Option<T extends string> = { value: T; label: string }

type Props<T extends string> = {
  value: T
  options: readonly Option<T>[]
  onChange: (value: T) => void
  label: string
}

export function Segmented<T extends string>({ value, options, onChange, label }: Props<T>) {
  return (
    <Tabs
      value={value}
      onValueChange={(next) => {
        const match = options.find((o) => o.value === next)
        if (match) onChange(match.value)
      }}
    >
      <TabsList aria-label={label} className="h-8 rounded-lg bg-secondary p-0.5 dark:bg-accent/60">
        {options.map((option) => (
          <TabsTrigger
            key={option.value}
            value={option.value}
            className="h-7 rounded-md px-3 text-[13px] data-[state=active]:bg-background data-[state=active]:shadow-sm"
          >
            {option.label}
          </TabsTrigger>
        ))}
      </TabsList>
    </Tabs>
  )
}

export const WINDOW_OPTIONS = [
  { value: "1h", label: "1H" },
  { value: "24h", label: "24H" },
  { value: "7d", label: "7D" },
] as const

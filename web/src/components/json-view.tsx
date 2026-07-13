import { cn } from "@/lib/utils"

export function JsonView({ value, className }: { value: unknown; className?: string }) {
  return (
    <pre
      className={cn(
        "max-h-80 overflow-auto rounded-lg bg-secondary p-3 font-mono text-[12px] leading-5 dark:bg-accent/40",
        className,
      )}
    >
      {JSON.stringify(value, null, 2)}
    </pre>
  )
}

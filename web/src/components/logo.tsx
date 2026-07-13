import { cn } from "@/lib/utils"

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" className={cn("size-7", className)}>
      <rect width="64" height="64" rx="14" className="fill-primary" />
      <path
        d="M18 22h18a8 8 0 0 1 0 16H26l12 10"
        fill="none"
        stroke="white"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="18" cy="38" r="3.5" fill="white" />
    </svg>
  )
}

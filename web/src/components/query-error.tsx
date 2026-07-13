"use client"

import { RotateCw, WifiOff } from "lucide-react"
import { EmptyState } from "@/components/empty-state"
import { Button } from "@/components/ui/button"
import { errorMessage } from "@/lib/api/client"
import { cn } from "@/lib/utils"

type Props = {
  error: unknown
  onRetry: () => unknown
  retrying?: boolean
  title?: string
  className?: string
}

export function QueryError({ error, onRetry, retrying = false, title = "Couldn’t load this", className }: Props) {
  return (
    <EmptyState
      icon={WifiOff}
      title={title}
      description={errorMessage(error)}
      className={cn("py-16", className)}
      action={
        <Button variant="outline" onClick={() => void onRetry()} disabled={retrying}>
          <RotateCw className={cn(retrying && "animate-spin motion-reduce:animate-none")} />
          Try Again
        </Button>
      }
    />
  )
}

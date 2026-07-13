"use client"

import { RotateCw, TriangleAlert } from "lucide-react"
import { EmptyState } from "@/components/empty-state"
import { Button } from "@/components/ui/button"

export default function ConsoleError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <EmptyState
      icon={TriangleAlert}
      title="Relay is unreachable"
      description="The console could not reach the Relay API. Check that it is running, then try again."
      className="min-h-[60vh]"
      action={
        <Button variant="outline" onClick={reset}>
          <RotateCw />
          Try Again
        </Button>
      }
    />
  )
}

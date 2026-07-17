"use client"

import { Check, Copy } from "lucide-react"
import { useState } from "react"
import { toast } from "sonner"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"

type Props = {
  value: string | (() => Promise<string>)
  label?: string
}

async function writeClipboard(value: Props["value"]) {
  if (typeof value === "string") return navigator.clipboard.writeText(value)
  // Handing the clipboard a pending blob keeps the user gesture alive while the value
  // loads; Safari rejects writeText once the click handler has awaited anything.
  if (typeof ClipboardItem !== "undefined") {
    const blob = value().then((text) => new Blob([text], { type: "text/plain" }))
    return navigator.clipboard.write([new ClipboardItem({ "text/plain": blob })])
  }
  return navigator.clipboard.writeText(await value())
}

export function CopyButton({ value, label = "Copy" }: Props) {
  const [copied, setCopied] = useState(false)
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          size="icon-sm"
          aria-label={label}
          onClick={async () => {
            try {
              await writeClipboard(value)
              setCopied(true)
              setTimeout(() => setCopied(false), 1500)
            } catch {
              toast.error("Couldn’t copy to the clipboard")
            }
          }}
        >
          {copied ? <Check className="text-success-text" /> : <Copy />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{copied ? "Copied" : label}</TooltipContent>
    </Tooltip>
  )
}

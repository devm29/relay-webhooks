import type { Metadata } from "next"
import { LiveView } from "./live-view"

export const metadata: Metadata = { title: "Live log" }

export default function LivePage() {
  return <LiveView />
}

import type { Metadata } from "next"
import { EndpointDetailView } from "./endpoint-detail-view"

export const metadata: Metadata = { title: "Endpoint" }

export default function EndpointDetailPage() {
  return <EndpointDetailView />
}

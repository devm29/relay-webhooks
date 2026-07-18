import type { Metadata } from "next"
import { Suspense } from "react"
import { DeliveriesView } from "./deliveries-view"

export const metadata: Metadata = { title: "Deliveries" }

export default function DeliveriesPage() {
  return (
    <Suspense>
      <DeliveriesView />
    </Suspense>
  )
}

import type { Metadata } from "next"
import { EventTypesView } from "./event-types-view"

export const metadata: Metadata = { title: "Event types" }

export default function EventTypesPage() {
  return <EventTypesView />
}

import { redirect } from "next/navigation"
import { EmptyState } from "@/components/empty-state"
import { PageHeader } from "@/components/shell/page-header"
import { NewAppButton } from "@/components/new-app-button"
import { app, page } from "@/lib/api/schemas"
import { serverRelay } from "@/lib/server/relay"
import { Boxes } from "lucide-react"

export default async function Home() {
  const apps = await serverRelay("/apps?limit=1", page(app))
  const first = apps.data[0]
  if (first) redirect(`/apps/${first.id}`)
  return (
    <>
      <PageHeader title="Welcome" />
      <EmptyState
        icon={Boxes}
        title="Create your first app"
        description="An app groups the endpoints and event types for one product. Most teams start with one per environment."
        action={<NewAppButton />}
      />
    </>
  )
}

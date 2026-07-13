import { cookies } from "next/headers"
import type { ReactNode } from "react"
import { AppSidebar } from "@/components/shell/app-sidebar"
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar"

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const store = await cookies()
  const open = store.get("sidebar_state")?.value !== "false"
  return (
    <SidebarProvider defaultOpen={open}>
      <AppSidebar />
      <SidebarInset className="min-w-0 bg-secondary/60 dark:bg-background">{children}</SidebarInset>
    </SidebarProvider>
  )
}

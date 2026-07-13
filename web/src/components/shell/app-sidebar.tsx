"use client"

import {
  Activity,
  Braces,
  ChevronsUpDown,
  Inbox,
  KeyRound,
  LayoutGrid,
  LogOut,
  Monitor,
  Moon,
  RotateCcw,
  Sun,
  Users,
  Webhook,
  type LucideIcon,
} from "lucide-react"
import Link from "next/link"
import { useParams, usePathname, useRouter } from "next/navigation"
import { useTheme } from "next-themes"
import { LogoMark } from "@/components/logo"
import { NewAppButton } from "@/components/new-app-button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSkeleton,
  SidebarRail,
} from "@/components/ui/sidebar"
import { useApps, useMe, useSignOut } from "@/lib/api/hooks"

type NavItem = { label: string; icon: LucideIcon; href: string }

function appNav(appId: string): NavItem[] {
  const base = `/apps/${appId}`
  return [
    { label: "Overview", icon: LayoutGrid, href: base },
    { label: "Live log", icon: Activity, href: `${base}/live` },
    { label: "Endpoints", icon: Webhook, href: `${base}/endpoints` },
    { label: "Messages", icon: Inbox, href: `${base}/messages` },
    { label: "Deliveries", icon: RotateCcw, href: `${base}/deliveries` },
    { label: "Event types", icon: Braces, href: `${base}/event-types` },
  ]
}

const ORG_NAV: NavItem[] = [
  { label: "API keys", icon: KeyRound, href: "/settings/api-keys" },
  { label: "Members", icon: Users, href: "/settings/members" },
]

function isActive(pathname: string, href: string, exact: boolean) {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`)
}

export function AppSidebar() {
  const params = useParams<{ appId?: string }>()
  const pathname = usePathname()
  const apps = useApps()
  const appId = params.appId ?? apps.data?.data[0]?.id
  const currentApp = apps.data?.data.find((a) => a.id === appId)

  return (
    <Sidebar collapsible="icon" className="border-r border-border/60">
      <SidebarHeader>
        <AppSwitcher currentName={currentApp?.name} />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-medium tracking-wide uppercase">
            App
          </SidebarGroupLabel>
          <div className="absolute top-3.5 right-3 group-data-[collapsible=icon]:hidden">
            <NewAppButton variant="ghost" />
          </div>
          <SidebarGroupContent>
            <SidebarMenu>
              {appId
                ? appNav(appId).map((item, index) => (
                    <NavLink key={item.href} item={item} active={isActive(pathname, item.href, index === 0)} />
                  ))
                : Array.from({ length: 6 }, (_, i) => (
                    <SidebarMenuItem key={i}>
                      <SidebarMenuSkeleton showIcon />
                    </SidebarMenuItem>
                  ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel className="text-[11px] font-medium tracking-wide uppercase">
            Organization
          </SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {ORG_NAV.map((item) => (
                <NavLink key={item.href} item={item} active={isActive(pathname, item.href, false)} />
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <UserMenu />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}

function NavLink({ item, active }: { item: NavItem; active: boolean }) {
  const Icon = item.icon
  return (
    <SidebarMenuItem>
      <SidebarMenuButton asChild isActive={active} tooltip={item.label} className="h-8 text-[13px]">
        <Link href={item.href} aria-current={active ? "page" : undefined}>
          <Icon strokeWidth={1.75} />
          <span>{item.label}</span>
        </Link>
      </SidebarMenuButton>
    </SidebarMenuItem>
  )
}

function AppSwitcher({ currentName }: { currentName: string | undefined }) {
  const apps = useApps()
  const me = useMe()
  const router = useRouter()
  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent">
              <LogoMark className="size-8 shrink-0" />
              <div className="grid flex-1 text-left leading-tight">
                <span className="truncate text-[13px] font-semibold">{me.data?.org.name ?? "Relay"}</span>
                <span className="truncate text-[12px] text-muted-foreground">{currentName ?? "Loading…"}</span>
              </div>
              <ChevronsUpDown className="ml-auto size-4 text-muted-foreground" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-60 rounded-xl" align="start" sideOffset={6}>
            <DropdownMenuLabel className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Apps
            </DropdownMenuLabel>
            {apps.data?.data.map((app) => (
              <DropdownMenuItem key={app.id} onSelect={() => router.push(`/apps/${app.id}`)}>
                {app.name}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

function UserMenu() {
  const me = useMe()
  const signOut = useSignOut()
  const { theme, setTheme } = useTheme()
  const user = me.data?.user
  const initials = (user?.name ?? "?")
    .split(" ")
    .map((part) => part[0] ?? "")
    .join("")
    .slice(0, 2)

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton size="lg" className="data-[state=open]:bg-sidebar-accent">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] font-semibold">
                {initials}
              </span>
              <div className="grid flex-1 text-left leading-tight">
                <span className="truncate text-[13px] font-medium">{user?.name ?? "…"}</span>
                <span className="truncate text-[12px] text-muted-foreground capitalize">{user?.role ?? ""}</span>
              </div>
              <ChevronsUpDown className="ml-auto size-4 text-muted-foreground" />
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent className="w-60 rounded-xl" side="top" align="start" sideOffset={6}>
            <DropdownMenuLabel className="font-normal">
              <div className="text-[13px] font-medium">{user?.name}</div>
              <div className="text-[12px] text-muted-foreground">{user?.email}</div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuLabel className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
              Appearance
            </DropdownMenuLabel>
            <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
              <DropdownMenuRadioItem value="light">
                <Sun /> Light
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="dark">
                <Moon /> Dark
              </DropdownMenuRadioItem>
              <DropdownMenuRadioItem value="system">
                <Monitor /> System
              </DropdownMenuRadioItem>
            </DropdownMenuRadioGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => signOut.mutate()}>
              <LogOut /> Sign out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}

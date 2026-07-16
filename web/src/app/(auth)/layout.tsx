import type { ReactNode } from "react"

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-secondary px-4 py-12 dark:bg-background">
      <div className="w-full max-w-[380px]">{children}</div>
    </main>
  )
}

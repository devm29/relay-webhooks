import type { Metadata } from "next"
import { Suspense } from "react"
import { AuthForm } from "@/components/auth-form"

export const metadata: Metadata = { title: "Sign in" }

export default function LoginPage() {
  return (
    <Suspense>
      <AuthForm mode="login" />
      <p className="mt-4 text-center text-[12px] text-muted-foreground">
        Demo workspace is pre-filled. Run <code className="font-mono">make seed</code> first.
      </p>
    </Suspense>
  )
}

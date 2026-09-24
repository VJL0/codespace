import { redirect } from "react-router"

import { GoogleSignInButton } from "@/components/google-signin-button"
import { getCurrentUser } from "@/lib/api"

export async function loader() {
  const user = await getCurrentUser()

  if (user !== null) {
    throw redirect("/")
  }

  return null
}

export function Component() {
  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            Continue with your Google account.
          </p>
        </div>

        <GoogleSignInButton className="w-full" />
      </div>
    </div>
  )
}

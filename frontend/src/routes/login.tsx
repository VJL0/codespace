import { redirect, useSearchParams } from "react-router"

import { OAuthSignInButton } from "@/components/oauth/oauth-sign-in-button"
import { OAUTH_PROVIDERS } from "@/components/oauth/providers"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { getCurrentUser } from "@/lib/api"
import { getOAuthErrorMessage } from "@/lib/oauth-errors"

export async function loader() {
  const user = await getCurrentUser()

  if (user !== null) {
    throw redirect("/")
  }

  return null
}

export function Component() {
  const [searchParams] = useSearchParams()
  const error = getOAuthErrorMessage(searchParams.get("error"))

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            Continue with one of your accounts.
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex w-full flex-col gap-2">
          {OAUTH_PROVIDERS.map((provider) => (
            <OAuthSignInButton
              key={provider.id}
              provider={provider}
              className="w-full"
            />
          ))}
        </div>
      </div>
    </div>
  )
}

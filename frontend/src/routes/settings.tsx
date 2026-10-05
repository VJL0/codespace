import { useState } from "react"
import {
  Link,
  useLoaderData,
  useNavigate,
  useRevalidator,
  useSearchParams,
} from "react-router"

import { OAUTH_PROVIDERS } from "@/components/oauth/providers"
import { ReauthenticateDialog } from "@/components/reauthenticate-dialog"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ApiError,
  getSignInMethods,
  linkProvider,
  logoutEverywhere,
  unlinkProvider,
  type OAuthProvider,
} from "@/lib/api"

export function loader() {
  return getSignInMethods()
}

// Codes the API's provider callback returns to /settings with as `?error=`.
const ERROR_MESSAGES: Record<string, string> = {
  oauth_failed: "That didn't complete at the provider. Try again.",
  identity_in_use: "That account is already linked to a different user.",
  provider_already_linked: "You already have an account with that provider.",
  link_failed: "You were signed out before linking finished. Try again.",
  reauth_failed:
    "We couldn't confirm it's you. Sign in again with your own account when asked.",
}

function providerLabel(provider: string | null): string | undefined {
  return OAUTH_PROVIDERS.find(({ id }) => id === provider)?.label
}

export function Component() {
  const methods = useLoaderData<typeof loader>()
  const [searchParams] = useSearchParams()
  const { revalidate } = useRevalidator()
  const navigate = useNavigate()
  const [reauthOpen, setReauthOpen] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  const linked = providerLabel(searchParams.get("linked"))
  const reauthenticated = providerLabel(searchParams.get("reauthenticated"))
  const errorCode = searchParams.get("error")
  const error =
    actionError ??
    (errorCode &&
      (ERROR_MESSAGES[errorCode] ?? "Something went wrong. Try again."))

  // Adding or removing a sign-in method needs a recent confirmation that
  // it's the user; ask for one when the API says so.
  async function guarded(action: () => Promise<void>) {
    setActionError(null)

    try {
      await action()
    } catch (caught) {
      if (
        caught instanceof ApiError &&
        caught.code === "reauthentication_required"
      ) {
        setReauthOpen(true)
      } else {
        setActionError(
          caught instanceof Error ? caught.message : "Something went wrong."
        )
      }
    }
  }

  async function unlink(provider: OAuthProvider) {
    await guarded(async () => {
      await unlinkProvider(provider)
      await revalidate()
    })
  }

  async function handleLogoutEverywhere() {
    await logoutEverywhere()
    navigate("/login", { replace: true })
  }

  const isOnlyMethod = methods.identities.length <= 1

  return (
    <div className="mx-auto flex min-h-svh w-full max-w-xl flex-col gap-6 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Settings</h1>
        <Link to="/" className={buttonVariants({ variant: "ghost" })}>
          Back
        </Link>
      </div>

      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      {!error && linked && (
        <Alert>
          <AlertDescription>{linked} is now linked.</AlertDescription>
        </Alert>
      )}
      {!error && reauthenticated && (
        <Alert>
          <AlertDescription>
            Confirmed. You can change your sign-in methods for the next few
            minutes.
          </AlertDescription>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Sign-in methods</CardTitle>
          <CardDescription>
            Accounts you can sign in with. Keep at least one.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ul className="flex flex-col divide-y">
            {OAUTH_PROVIDERS.map((provider) => {
              const identity = methods.identities.find(
                ({ provider: id }) => id === provider.id
              )

              return (
                <li
                  key={provider.id}
                  aria-label={provider.label}
                  className="flex items-center gap-3 py-3"
                >
                  <provider.Logo />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <span className="font-medium">{provider.label}</span>
                    <span className="truncate text-sm text-muted-foreground">
                      {identity
                        ? (identity.email_snapshot ?? "Linked")
                        : "Not linked"}
                    </span>
                  </div>
                  {identity ? (
                    <Button
                      variant="outline"
                      disabled={isOnlyMethod}
                      title={
                        isOnlyMethod
                          ? "This is your only way to sign in."
                          : undefined
                      }
                      onClick={() => unlink(provider.id)}
                    >
                      Unlink
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      onClick={() => guarded(() => linkProvider(provider.id))}
                    >
                      Link
                    </Button>
                  )}
                </li>
              )
            })}
          </ul>
        </CardContent>
      </Card>

      {methods.emails.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Email addresses</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-1 text-sm">
              {methods.emails.map(({ email, is_primary }) => (
                <li key={email}>
                  {email}
                  {is_primary && (
                    <span className="text-muted-foreground"> · Primary</span>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Sessions</CardTitle>
          <CardDescription>
            Sign out of every browser you're signed in on, this one included.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={handleLogoutEverywhere}>
            Log out everywhere
          </Button>
        </CardContent>
      </Card>

      <ReauthenticateDialog
        open={reauthOpen}
        onOpenChange={setReauthOpen}
        providers={methods.reauthentication_providers}
      />
    </div>
  )
}

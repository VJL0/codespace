import {
  Form,
  Link,
  redirect,
  useActionData,
  useNavigation,
  useSearchParams,
  type ActionFunctionArgs,
} from "react-router"

import { OAuthSignInButton } from "@/components/oauth/oauth-sign-in-button"
import { OAUTH_PROVIDERS } from "@/components/oauth/providers"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { attempt, getCurrentUser, loginWithPassword } from "@/lib/api"
import { getOAuthErrorMessage } from "@/lib/oauth-errors"

export async function loader() {
  const user = await getCurrentUser()

  if (user !== null) {
    throw redirect("/")
  }

  return null
}

export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData()
  const failed = await attempt(() =>
    loginWithPassword(String(form.get("email")), String(form.get("password")))
  )

  return failed ?? redirect("/")
}

export function Component() {
  const [searchParams] = useSearchParams()
  const failed = useActionData<typeof action>()
  const submitting = useNavigation().state !== "idle"
  const error = failed?.error ?? getOAuthErrorMessage(searchParams.get("error"))

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="space-y-1 text-center">
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="text-sm text-muted-foreground">
            New here?{" "}
            <Link to="/signup" className="underline underline-offset-4">
              Create an account
            </Link>
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Form method="post" replace>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                name="email"
                type="email"
                autoComplete="username"
                required
              />
            </Field>
            <Field>
              <div className="flex items-center justify-between">
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Link
                  to="/forgot-password"
                  className="text-sm underline-offset-4 hover:underline"
                >
                  Forgot password?
                </Link>
              </div>
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
              />
            </Field>
            <Button type="submit" size="lg" disabled={submitting}>
              Sign in
            </Button>
          </FieldGroup>
        </Form>

        <FieldSeparator>or</FieldSeparator>

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

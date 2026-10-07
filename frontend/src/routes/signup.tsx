import {
  Form,
  Link,
  redirect,
  useActionData,
  useNavigation,
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
import { attempt, getCurrentUser, register } from "@/lib/api"

export async function loader() {
  if ((await getCurrentUser()) !== null) {
    throw redirect("/")
  }

  return null
}

export async function action({ request }: ActionFunctionArgs) {
  const email = String((await request.formData()).get("email"))

  return (await attempt(() => register(email))) ?? { sentTo: email }
}

export function Component() {
  const result = useActionData<typeof action>()
  const submitting = useNavigation().state !== "idle"

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="space-y-1 text-center">
          <h1 className="text-xl font-semibold">Create an account</h1>
          <p className="text-sm text-muted-foreground">
            Already have one?{" "}
            <Link to="/login" className="underline underline-offset-4">
              Sign in
            </Link>
          </p>
        </div>

        {result && "sentTo" in result ? (
          <Alert>
            <AlertDescription>
              Check {result.sentTo} for a link to finish creating your account.
              It works for an hour.
            </AlertDescription>
          </Alert>
        ) : (
          <>
            <Form method="post">
              <FieldGroup>
                {result?.error && (
                  <Alert variant="destructive">
                    <AlertDescription>{result.error}</AlertDescription>
                  </Alert>
                )}
                <Field>
                  <FieldLabel htmlFor="email">Email</FieldLabel>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    autoComplete="email"
                    required
                  />
                </Field>
                <Button type="submit" size="lg" disabled={submitting}>
                  Continue with email
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
          </>
        )}
      </div>
    </div>
  )
}

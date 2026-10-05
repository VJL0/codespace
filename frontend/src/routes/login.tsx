import { useState, type SubmitEvent } from "react"
import { Link, redirect, useNavigate, useSearchParams } from "react-router"

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
import { getCurrentUser, loginWithPassword } from "@/lib/api"
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
  const navigate = useNavigate()
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const error = formError ?? getOAuthErrorMessage(searchParams.get("error"))

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)

    try {
      await loginWithPassword(email, password)
      navigate("/", { replace: true })
    } catch (caught) {
      setFormError(caught instanceof Error ? caught.message : "Try again.")
      setSubmitting(false)
    }
  }

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

        <form onSubmit={handleSubmit}>
          <FieldGroup>
            <Field>
              <FieldLabel htmlFor="email">Email</FieldLabel>
              <Input
                id="email"
                type="email"
                autoComplete="username"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
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
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </Field>
            <Button type="submit" size="lg" disabled={submitting}>
              Sign in
            </Button>
          </FieldGroup>
        </form>

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

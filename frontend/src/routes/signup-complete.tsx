import { useState, type SubmitEvent } from "react"
import { Link, useNavigate } from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { ApiError, completeRegistration, tokenFromLocation } from "@/lib/api"

export function Component() {
  const navigate = useNavigate()
  const [token] = useState(tokenFromLocation)
  const [name, setName] = useState("")
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()

    if (token === null) {
      return
    }

    setSubmitting(true)
    setError(null)

    try {
      await completeRegistration({ token, name, password })
      navigate("/", { replace: true })
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Try again."))
      setSubmitting(false)
    }
  }

  const linkUnusable =
    token === null ||
    (error instanceof ApiError && error.code === "invalid_token")

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold">
          Finish creating your account
        </h1>

        {linkUnusable ? (
          <Alert variant="destructive">
            <AlertDescription>
              This link has expired or was already used.{" "}
              <Link to="/signup" className="underline underline-offset-4">
                Sign up again
              </Link>
              .
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={handleSubmit}>
            <FieldGroup>
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error.message}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor="name">Name</FieldLabel>
                <Input
                  id="name"
                  autoComplete="name"
                  required
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                />
              </Field>
              <Field>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={15}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
                <FieldDescription>
                  At least 15 characters. A few words make a good one.
                </FieldDescription>
              </Field>
              <Button type="submit" size="lg" disabled={submitting}>
                Create account
              </Button>
            </FieldGroup>
          </form>
        )}
      </div>
    </div>
  )
}

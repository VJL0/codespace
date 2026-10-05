import { useState, type SubmitEvent } from "react"
import { Link, redirect } from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { getCurrentUser, register } from "@/lib/api"

export async function loader() {
  if ((await getCurrentUser()) !== null) {
    throw redirect("/")
  }

  return null
}

export function Component() {
  const [email, setEmail] = useState("")
  const [sentTo, setSentTo] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await register(email)
      setSentTo(email)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Try again.")
    } finally {
      setSubmitting(false)
    }
  }

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

        {sentTo ? (
          <Alert>
            <AlertDescription>
              Check {sentTo} for a link to finish creating your account. It
              works for an hour.
            </AlertDescription>
          </Alert>
        ) : (
          <form onSubmit={handleSubmit}>
            <FieldGroup>
              {error && (
                <Alert variant="destructive">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </Field>
              <Button type="submit" size="lg" disabled={submitting}>
                Email me a link
              </Button>
            </FieldGroup>
          </form>
        )}
      </div>
    </div>
  )
}

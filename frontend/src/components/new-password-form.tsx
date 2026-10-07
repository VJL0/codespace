import { useState, type SubmitEvent } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"

interface NewPasswordFormProps {
  submitLabel: string
  onSubmit: (password: string) => Promise<void>
}

// Choosing a password from an emailed link: resetting or adding one.
export function NewPasswordForm({
  submitLabel,
  onSubmit,
}: NewPasswordFormProps) {
  const [password, setPassword] = useState("")
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      await onSubmit(password)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Try again.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <FieldGroup>
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Field>
          <FieldLabel htmlFor="new-password">New password</FieldLabel>
          <Input
            id="new-password"
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
          {submitLabel}
        </Button>
      </FieldGroup>
    </form>
  )
}

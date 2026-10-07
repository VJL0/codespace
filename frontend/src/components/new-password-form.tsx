import { Form, useNavigation } from "react-router"

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
  // The emailed link's secret, posted with the password.
  token: string
  error: string | undefined
  submitLabel: string
}

// Choosing a password from an emailed link: resetting or adding one. Posts
// `token` and `password` to the route's action.
export function NewPasswordForm({
  token,
  error,
  submitLabel,
}: NewPasswordFormProps) {
  const submitting = useNavigation().state !== "idle"

  return (
    <Form method="post">
      <input type="hidden" name="token" value={token} />
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
            name="password"
            type="password"
            autoComplete="new-password"
            required
            minLength={15}
          />
          <FieldDescription>
            At least 15 characters. A few words make a good one.
          </FieldDescription>
        </Field>
        <Button type="submit" size="lg" disabled={submitting}>
          {submitLabel}
        </Button>
      </FieldGroup>
    </Form>
  )
}

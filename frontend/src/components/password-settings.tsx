import { useState, type SubmitEvent } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { changePassword, removePassword, startPasswordSetup } from "@/lib/api"

interface PasswordSettingsProps {
  hasPassword: boolean
  // The primary email, which signing in with a password uses.
  email: string | null
  // Whether the password is the user's only way to sign in.
  isOnlyMethod: boolean
  // Runs an action that may need the user to confirm it's them first.
  guarded: (action: () => Promise<void>) => Promise<void>
  onChanged: () => Promise<void>
}

export function PasswordSettings({
  hasPassword,
  email,
  isOnlyMethod,
  guarded,
  onChanged,
}: PasswordSettingsProps) {
  const [current, setCurrent] = useState("")
  const [next, setNext] = useState("")
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleChange(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setNotice(null)

    try {
      await changePassword(current, next)
      setCurrent("")
      setNext("")
      setNotice("Password changed. Your other browsers were signed out.")
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Try again.")
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Password</CardTitle>
        <CardDescription>
          {hasPassword
            ? "You can sign in with your email and password."
            : "Add one to also sign in with your email."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {notice && (
          <Alert>
            <AlertDescription>{notice}</AlertDescription>
          </Alert>
        )}
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {hasPassword ? (
          <>
            <form onSubmit={handleChange}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="current-password">
                    Current password
                  </FieldLabel>
                  <Input
                    id="current-password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={current}
                    onChange={(event) => setCurrent(event.target.value)}
                  />
                </Field>
                <Field>
                  <FieldLabel htmlFor="next-password">New password</FieldLabel>
                  <Input
                    id="next-password"
                    type="password"
                    autoComplete="new-password"
                    required
                    minLength={15}
                    value={next}
                    onChange={(event) => setNext(event.target.value)}
                  />
                  <FieldDescription>At least 15 characters.</FieldDescription>
                </Field>
                <Button type="submit" variant="outline">
                  Change password
                </Button>
              </FieldGroup>
            </form>
            <Button
              variant="outline"
              disabled={isOnlyMethod}
              title={
                isOnlyMethod ? "This is your only way to sign in." : undefined
              }
              onClick={() =>
                guarded(async () => {
                  await removePassword()
                  await onChanged()
                })
              }
            >
              Remove password
            </Button>
          </>
        ) : (
          <Button
            variant="outline"
            disabled={email === null}
            title={
              email === null
                ? "A password needs an email address to sign in with."
                : undefined
            }
            onClick={() =>
              guarded(async () => {
                await startPasswordSetup()
                setNotice(
                  `We sent a link to ${email}. Open it to choose your password.`
                )
              })
            }
          >
            Add a password
          </Button>
        )}
      </CardContent>
    </Card>
  )
}

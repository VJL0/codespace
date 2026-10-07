import { useState, type SubmitEvent } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Field,
  FieldGroup,
  FieldLabel,
  FieldSeparator,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import {
  errorMessage,
  reauthenticateWithPassword,
  sendReauthenticationEmail,
} from "@/lib/api"

interface ReauthenticateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  hasPassword: boolean
  // The primary email a link can be sent to, if any.
  email: string | null
  // After confirming without leaving the page (a password).
  onConfirmed: () => void
}

// Shown when the API answers `reauthentication_required`: changing sign-in
// methods needs proof, from the last few minutes, that it's really the user.
export function ReauthenticateDialog({
  open,
  onOpenChange,
  hasPassword,
  email,
  onConfirmed,
}: ReauthenticateDialogProps) {
  const [password, setPassword] = useState("")
  const [emailSent, setEmailSent] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function attempt(action: () => Promise<void>) {
    setError(null)

    try {
      await action()
    } catch (caught) {
      setError(errorMessage(caught))
    }
  }

  async function handlePassword(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    await attempt(async () => {
      await reauthenticateWithPassword(password)
      setPassword("")
      onConfirmed()
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm it's you</DialogTitle>
          <DialogDescription>
            {hasPassword || email
              ? "Changing how you sign in needs a fresh confirmation."
              : "Confirming it's you needs a password or an email address, and your account has neither."}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex flex-col gap-4">
          {hasPassword && (
            <form onSubmit={handlePassword}>
              <FieldGroup>
                <Field>
                  <FieldLabel htmlFor="reauth-password">Password</FieldLabel>
                  <Input
                    id="reauth-password"
                    type="password"
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                  />
                </Field>
                <Button type="submit">Confirm</Button>
              </FieldGroup>
            </form>
          )}

          {hasPassword && email && <FieldSeparator>or</FieldSeparator>}

          {email &&
            (emailSent ? (
              <p className="text-sm text-muted-foreground">
                We sent a link to {email}. Open it in this browser.
              </p>
            ) : (
              <Button
                variant="outline"
                size="lg"
                onClick={() =>
                  attempt(async () => {
                    await sendReauthenticationEmail()
                    setEmailSent(true)
                  })
                }
              >
                Email me a link
              </Button>
            ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

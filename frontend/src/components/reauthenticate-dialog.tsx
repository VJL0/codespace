import { useState } from "react"

import { OAUTH_PROVIDERS } from "@/components/oauth/providers"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { reauthenticateWith, type OAuthProvider } from "@/lib/api"

interface ReauthenticateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  // Linked providers that can make the user enter their credentials again.
  providers: OAuthProvider[]
}

// Shown when the API answers `reauthentication_required`: changing sign-in
// methods needs proof, from the last few minutes, that it's really the user.
export function ReauthenticateDialog({
  open,
  onOpenChange,
  providers,
}: ReauthenticateDialogProps) {
  const [error, setError] = useState<string | null>(null)
  const options = OAUTH_PROVIDERS.filter(({ id }) => providers.includes(id))

  async function confirmWith(provider: OAuthProvider) {
    setError(null)

    try {
      await reauthenticateWith(provider)
    } catch {
      setError("That didn't work. Try again.")
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Confirm it's you</DialogTitle>
          <DialogDescription>
            {options.length > 0
              ? "Sign in again to continue. You'll be asked for your password, even if you're already signed in there."
              : "None of your sign-in methods can confirm it's you yet: GitHub can't be made to ask for your password again."}
          </DialogDescription>
        </DialogHeader>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="flex flex-col gap-2">
          {options.map((provider) => (
            <Button
              key={provider.id}
              variant="outline"
              size="lg"
              className="gap-3"
              onClick={() => confirmWith(provider.id)}
            >
              <provider.Logo />
              Continue with {provider.label}
            </Button>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}

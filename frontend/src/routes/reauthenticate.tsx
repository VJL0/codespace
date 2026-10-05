import { useEffect, useState } from "react"
import { Link, useNavigate } from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { completeEmailReauthentication, tokenFromLocation } from "@/lib/api"

// Where the "Confirm it's you" email links to. It only works in the browser
// that asked for it.
export function Component() {
  const navigate = useNavigate()
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const token = tokenFromLocation()

    if (token === null) {
      return
    }

    completeEmailReauthentication(token).then(
      () => navigate("/settings?reauthenticated=email", { replace: true }),
      (caught) =>
        setError(caught instanceof Error ? caught.message : "Try again.")
    )
  }, [navigate])

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="w-full max-w-sm">
        {error || tokenFromLocation() === null ? (
          <Alert variant="destructive">
            <AlertDescription>
              {error ?? "This link is incomplete."}{" "}
              <Link to="/settings" className="underline underline-offset-4">
                Back to settings
              </Link>
            </AlertDescription>
          </Alert>
        ) : (
          <p className="text-center text-sm text-muted-foreground">
            Confirming it's you…
          </p>
        )}
      </div>
    </div>
  )
}

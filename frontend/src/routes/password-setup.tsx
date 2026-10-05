import { useState } from "react"
import { Link } from "react-router"

import { NewPasswordForm } from "@/components/new-password-form"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { completePasswordSetup, tokenFromLocation } from "@/lib/api"

// Where the "Add a password" email links to.
export function Component() {
  const [token] = useState(tokenFromLocation)
  const [done, setDone] = useState(false)

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold">Add a password</h1>

        {done ? (
          <Alert>
            <AlertDescription>
              Password added. You can now also sign in with your email.{" "}
              <Link to="/settings" className="underline underline-offset-4">
                Back to settings
              </Link>
            </AlertDescription>
          </Alert>
        ) : token === null ? (
          <Alert variant="destructive">
            <AlertDescription>This link is incomplete.</AlertDescription>
          </Alert>
        ) : (
          <NewPasswordForm
            submitLabel="Add password"
            onSubmit={async (password) => {
              await completePasswordSetup(token, password)
              setDone(true)
            }}
          />
        )}
      </div>
    </div>
  )
}

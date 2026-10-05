import { useState } from "react"
import { Link } from "react-router"

import { NewPasswordForm } from "@/components/new-password-form"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { resetPassword, tokenFromLocation } from "@/lib/api"

export function Component() {
  const [token] = useState(tokenFromLocation)
  const [done, setDone] = useState(false)

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold">
          Choose a new password
        </h1>

        {done ? (
          <Alert>
            <AlertDescription>
              Your password is changed and you're signed out everywhere.{" "}
              <Link to="/login" className="underline underline-offset-4">
                Sign in
              </Link>
            </AlertDescription>
          </Alert>
        ) : token === null ? (
          <Alert variant="destructive">
            <AlertDescription>This link is incomplete.</AlertDescription>
          </Alert>
        ) : (
          <NewPasswordForm
            submitLabel="Reset password"
            onSubmit={async (password) => {
              await resetPassword(token, password)
              setDone(true)
            }}
          />
        )}
      </div>
    </div>
  )
}

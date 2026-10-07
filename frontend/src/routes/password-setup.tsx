import { useState } from "react"
import { Link, useActionData, type ActionFunctionArgs } from "react-router"

import { NewPasswordForm } from "@/components/new-password-form"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { attempt, completePasswordSetup, tokenFromLocation } from "@/lib/api"

export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData()
  const failed = await attempt(() =>
    completePasswordSetup(
      String(form.get("token")),
      String(form.get("password"))
    )
  )

  return failed ?? { done: true }
}

// Where the "Add a password" email links to.
export function Component() {
  const [token] = useState(tokenFromLocation)
  const result = useActionData<typeof action>()

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold">Add a password</h1>

        {result && "done" in result ? (
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
            token={token}
            error={result?.error}
            submitLabel="Add password"
          />
        )}
      </div>
    </div>
  )
}

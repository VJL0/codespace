import { useState } from "react"
import {
  Form,
  Link,
  redirect,
  useActionData,
  useNavigation,
  type ActionFunctionArgs,
} from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Field,
  FieldDescription,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { attempt, completeRegistration, tokenFromLocation } from "@/lib/api"

export async function action({ request }: ActionFunctionArgs) {
  const form = await request.formData()
  const failed = await attempt(() =>
    completeRegistration({
      token: String(form.get("token")),
      name: String(form.get("name")),
      password: String(form.get("password")),
    })
  )

  return failed ?? redirect("/")
}

export function Component() {
  const [token] = useState(tokenFromLocation)
  const failed = useActionData<typeof action>()
  const submitting = useNavigation().state !== "idle"

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <h1 className="text-center text-xl font-semibold">
          Finish creating your account
        </h1>

        {token === null || failed?.code === "invalid_token" ? (
          <Alert variant="destructive">
            <AlertDescription>
              This link has expired or was already used.{" "}
              <Link to="/signup" className="underline underline-offset-4">
                Sign up again
              </Link>
              .
            </AlertDescription>
          </Alert>
        ) : (
          <Form method="post" replace>
            <input type="hidden" name="token" value={token} />
            <FieldGroup>
              {failed && (
                <Alert variant="destructive">
                  <AlertDescription>{failed.error}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor="name">Name</FieldLabel>
                <Input id="name" name="name" autoComplete="name" required />
              </Field>
              <Field>
                <FieldLabel htmlFor="password">Password</FieldLabel>
                <Input
                  id="password"
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
                Create account
              </Button>
            </FieldGroup>
          </Form>
        )}
      </div>
    </div>
  )
}

import {
  Form,
  Link,
  useActionData,
  useNavigation,
  type ActionFunctionArgs,
} from "react-router"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldGroup, FieldLabel } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { attempt, forgotPassword } from "@/lib/api"

export async function action({ request }: ActionFunctionArgs) {
  const email = String((await request.formData()).get("email"))

  return (await attempt(() => forgotPassword(email))) ?? { sentTo: email }
}

export function Component() {
  const result = useActionData<typeof action>()
  const submitting = useNavigation().state !== "idle"

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col gap-6">
        <div className="space-y-1 text-center">
          <h1 className="text-xl font-semibold">Reset your password</h1>
          <p className="text-sm text-muted-foreground">
            <Link to="/login" className="underline underline-offset-4">
              Back to sign in
            </Link>
          </p>
        </div>

        {result && "sentTo" in result ? (
          <Alert>
            <AlertDescription>
              If {result.sentTo} has an account with a password, we've sent it a
              link to reset it. It works for 30 minutes.
            </AlertDescription>
          </Alert>
        ) : (
          <Form method="post">
            <FieldGroup>
              {result?.error && (
                <Alert variant="destructive">
                  <AlertDescription>{result.error}</AlertDescription>
                </Alert>
              )}
              <Field>
                <FieldLabel htmlFor="email">Email</FieldLabel>
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                />
              </Field>
              <Button type="submit" size="lg" disabled={submitting}>
                Email me a link
              </Button>
            </FieldGroup>
          </Form>
        )}
      </div>
    </div>
  )
}

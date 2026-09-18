import { GoogleSignInButton } from "@/components/google-signin-button"

export function Component() {
  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="flex w-full max-w-sm flex-col items-center gap-6 text-center">
        <div className="space-y-1">
          <h1 className="text-xl font-semibold">Sign in</h1>
          <p className="text-muted-foreground text-sm">
            Continue with your Google account.
          </p>
        </div>

        <GoogleSignInButton className="w-full" />
      </div>
    </div>
  )
}

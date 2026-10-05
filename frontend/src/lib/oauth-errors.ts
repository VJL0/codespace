// Error codes the backend's OAuth callback redirects back with as `?error=`.
const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  oauth_failed: "Sign-in was cancelled or didn't complete. Try again.",
  account_exists:
    "An account with this email already exists. Sign in with the account you used before.",
}

export function getOAuthErrorMessage(code: string | null): string | null {
  if (code === null) {
    return null
  }

  return OAUTH_ERROR_MESSAGES[code] ?? "Something went wrong. Try again."
}

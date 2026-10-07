export type OAuthProvider = "google" | "microsoft" | "github"

export interface CurrentUser {
  name: string | null
  // Null when no provider vouched for an address.
  email: string | null
  avatar_url: string | null
}

// A response the API refused; `code` is its machine-readable reason, if any.
export class ApiError extends Error {
  readonly status: number
  readonly code: string | null

  constructor(status: number, code: string | null, message: string) {
    super(message)
    this.status = status
    this.code = code
  }
}

// fetch() for the API, which shares the SPA's origin, so cookies go along
// by default, and the browser's Sec-Fetch-Site header passes the API's CSRF
// check.
export async function apiFetch(
  path: string,
  { json, headers, ...init }: RequestInit & { json?: unknown } = {}
): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    headers: {
      ...(json === undefined ? {} : { "Content-Type": "application/json" }),
      ...headers,
    },
    body: json === undefined ? init.body : JSON.stringify(json),
  })

  if (!response.ok) {
    const detail = await response
      .json()
      .then((body) => body?.detail)
      .catch(() => null)
    // Either a plain message, or {code, message} for errors the SPA acts on.
    const code = typeof detail?.code === "string" ? detail.code : null
    const message =
      typeof detail === "string"
        ? detail
        : typeof detail?.message === "string"
          ? detail.message
          : `Request failed (${response.status}).`

    throw new ApiError(response.status, code, message)
  }

  return response
}

// What to show for a failed request.
export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Try again."
}

// For a route action: make the API call, and turn a refusal into data for
// the page to show rather than an error for the route's error boundary.
// Null when the call succeeded.
export async function attempt(
  call: () => Promise<unknown>
): Promise<{ error: string; code: string | null } | null> {
  try {
    await call()

    return null
  } catch (caught) {
    return {
      error: errorMessage(caught),
      code: caught instanceof ApiError ? caught.code : null,
    }
  }
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    const response = await apiFetch("/api/auth/me")

    return await response.json()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      return null
    }

    throw error
  }
}

export async function logout(): Promise<void> {
  await apiFetch("/api/auth/logout", { method: "POST" })
}

export async function logoutEverywhere(): Promise<void> {
  await apiFetch("/api/auth/logout-all", { method: "POST" })
}

export interface SignInMethods {
  has_password: boolean
  identities: {
    provider: OAuthProvider
    email_snapshot: string | null
    created_at: string
  }[]
  emails: { email: string; is_primary: boolean; verified: boolean }[]
  // Linked providers that can confirm it's the user by asking for their
  // credentials again.
  reauthentication_providers: OAuthProvider[]
  recently_authenticated: boolean
}

export async function getSignInMethods(): Promise<SignInMethods> {
  return (await apiFetch("/api/auth/methods")).json()
}

// Linking and reauthenticating continue at the provider, which returns the
// browser to /settings.
async function continueAtProvider(
  provider: OAuthProvider,
  purpose: "link" | "reauthenticate"
): Promise<void> {
  const response = await apiFetch(`/api/auth/${provider}/${purpose}`, {
    method: "POST",
  })
  const { authorization_url } = await response.json()

  window.location.assign(authorization_url)
}

export function linkProvider(provider: OAuthProvider): Promise<void> {
  return continueAtProvider(provider, "link")
}

export function reauthenticateWith(provider: OAuthProvider): Promise<void> {
  return continueAtProvider(provider, "reauthenticate")
}

export async function unlinkProvider(provider: OAuthProvider): Promise<void> {
  await apiFetch(`/api/auth/identities/${provider}`, { method: "DELETE" })
}

// Email-first sign-up: this only sends a link; the account is created when
// it's opened (completeRegistration).
export async function register(email: string): Promise<void> {
  await apiFetch("/api/auth/register", { method: "POST", json: { email } })
}

export async function completeRegistration(details: {
  token: string
  name: string
  password: string
}): Promise<void> {
  await apiFetch("/api/auth/register/complete", {
    method: "POST",
    json: details,
  })
}

export async function loginWithPassword(
  email: string,
  password: string
): Promise<void> {
  await apiFetch("/api/auth/login", {
    method: "POST",
    json: { email, password },
  })
}

export async function reauthenticateWithPassword(
  password: string
): Promise<void> {
  await apiFetch("/api/auth/reauthenticate", {
    method: "POST",
    json: { password },
  })
}

export async function sendReauthenticationEmail(): Promise<void> {
  await apiFetch("/api/auth/reauthenticate/email", { method: "POST" })
}

export async function completeEmailReauthentication(
  token: string
): Promise<void> {
  await apiFetch("/api/auth/reauthenticate/email/complete", {
    method: "POST",
    json: { token },
  })
}

// The secret an emailed link carries in its #token= fragment, which never
// reaches a server.
export function tokenFromLocation(): string | null {
  return new URLSearchParams(window.location.hash.slice(1)).get("token")
}

export async function forgotPassword(email: string): Promise<void> {
  await apiFetch("/api/auth/password/forgot", {
    method: "POST",
    json: { email },
  })
}

export async function resetPassword(
  token: string,
  password: string
): Promise<void> {
  await apiFetch("/api/auth/password/reset", {
    method: "POST",
    json: { token, password },
  })
}

// Adding a password to a provider-only account goes by a link to its email.
export async function startPasswordSetup(): Promise<void> {
  await apiFetch("/api/auth/password/setup", { method: "POST" })
}

export async function completePasswordSetup(
  token: string,
  password: string
): Promise<void> {
  await apiFetch("/api/auth/password/setup/complete", {
    method: "POST",
    json: { token, password },
  })
}

export async function changePassword(
  currentPassword: string,
  newPassword: string
): Promise<void> {
  await apiFetch("/api/auth/password/change", {
    method: "POST",
    json: { current_password: currentPassword, new_password: newPassword },
  })
}

export async function removePassword(): Promise<void> {
  await apiFetch("/api/auth/password", { method: "DELETE" })
}

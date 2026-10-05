export type OAuthProvider = "google" | "microsoft" | "github"

export interface CurrentUser {
  name: string | null
  email: string
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
// by default. The custom header is what the API's CSRF check requires on
// state-changing requests; a cross-site page can't send it.
export async function apiFetch(
  path: string,
  { json, headers, ...init }: RequestInit & { json?: unknown } = {}
): Promise<Response> {
  const response = await fetch(path, {
    ...init,
    headers: {
      "X-CSRF-Protection": "1",
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
    const code = typeof detail?.code === "string" ? detail.code : null
    const message =
      typeof detail === "string"
        ? detail
        : `Request failed (${response.status}).`

    throw new ApiError(response.status, code, message)
  }

  return response
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

import { test, type BrowserContext, type Page } from "@playwright/test"

export { expect, test } from "@playwright/test"

export type Provider = "google" | "microsoft" | "github"

// Keyword arguments for the backend's FakeOAuthServer.authorize: who the
// provider says signed in, or the `error` it answers with.
export type ProviderResponse = Record<string, unknown>

export interface TestIdentity {
  provider: Provider
  name: string
  email: string
  response: ProviderResponse
}

const PROVIDER_LABELS: Record<Provider, string> = {
  google: "Google",
  microsoft: "Microsoft",
  github: "GitHub",
}

// The fake signs work/school Microsoft tokens for this tenant
// (backend/tests/support/fake_oauth.py).
const MICROSOFT_ORG_TENANT = "aaaabbbb-0000-cccc-1111-dddd2222eeee"

// A provider account no other test uses, so tests can share the database
// and run in parallel.
export function newIdentity(provider: Provider): TestIdentity {
  const id = crypto.randomUUID()
  const name = `Test User ${id.slice(0, 8)}`
  const email = `user-${id}@example.com`

  const response = {
    google: {
      claims: { sub: id, email, email_verified: true, name },
    },
    microsoft: {
      claims: {
        sub: `pairwise-${id}`,
        oid: id,
        tid: MICROSOFT_ORG_TENANT,
        email,
        xms_edov: true,
        name,
      },
    },
    github: {
      github_user: {
        id: Math.floor(Math.random() * 2 ** 31),
        login: `user-${id.slice(0, 8)}`,
        name,
      },
      github_emails: [
        { email, primary: true, verified: true, visibility: null },
      ],
    },
  }[provider]

  return { provider, name, email, response }
}

const PROVIDER_HOSTS = [
  "accounts.google.com",
  "login.microsoftonline.com",
  "github.com",
]

// The providers' authorization pages aren't reachable from tests, so where
// the API redirects the browser to one, send it to the API's test-only
// stand-in instead, which answers as `response`. Playwright doesn't route
// requests that follow a redirect, so this rewrites the API's redirect
// rather than the provider request.
export async function answerProvidersWith(
  context: BrowserContext,
  response: ProviderResponse
): Promise<void> {
  const baseURL = test.info().project.use.baseURL

  await context.route("**/api/auth/*/login", async (route) => {
    // The real response, so its OAuth state cookie is still set.
    const login = await route.fetch({ maxRedirects: 0 })
    const location = login.headers()["location"] ?? ""

    if (!PROVIDER_HOSTS.includes(new URL(location, baseURL).hostname)) {
      return route.fulfill({ response: login })
    }

    const approve = new URL("/api/__e2e__/oauth/authorize", baseURL)
    approve.search = new URLSearchParams({
      url: location,
      scenario: JSON.stringify(response),
    }).toString()

    return route.fulfill({
      response: login,
      headers: { ...login.headers(), location: approve.toString() },
    })
  })
}

export async function signInWith(
  page: Page,
  provider: Provider,
  response: ProviderResponse
): Promise<void> {
  await answerProvidersWith(page.context(), response)
  await page.goto("/login")
  await page
    .getByRole("link", { name: `Sign in with ${PROVIDER_LABELS[provider]}` })
    .click()
}

export async function signIn(
  page: Page,
  identity: TestIdentity
): Promise<void> {
  await signInWith(page, identity.provider, identity.response)
  await page.waitForURL("/")
}

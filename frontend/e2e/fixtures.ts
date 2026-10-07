import { expect, test, type BrowserContext, type Page } from "@playwright/test"

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

const PROVIDER_BY_HOST: Record<string, Provider> = {
  "accounts.google.com": "google",
  "login.microsoftonline.com": "microsoft",
  "github.com": "github",
}

// How each provider answers, for those a test expects to be asked.
export type ProviderResponses = Partial<Record<Provider, ProviderResponse>>

// The providers' authorization pages aren't reachable from tests, so send
// the browser to the API's test-only stand-in instead, which answers as the
// test says. Later calls take precedence; a provider a call has no answer
// for falls through to earlier ones.
export async function answerProvidersWith(
  context: BrowserContext,
  responses: ProviderResponses
): Promise<void> {
  const baseURL = test.info().project.use.baseURL

  function approval(providerUrl: string): string | null {
    const provider = PROVIDER_BY_HOST[new URL(providerUrl, baseURL).hostname]
    const response = provider && responses[provider]

    if (!response) {
      return null
    }

    const approve = new URL("/api/__e2e__/oauth/authorize", baseURL)
    approve.search = new URLSearchParams({
      url: providerUrl,
      scenario: JSON.stringify(response),
    }).toString()

    return approve.toString()
  }

  // Sign-in: the API redirects to the provider, and Playwright doesn't
  // route requests that follow a redirect, so rewrite the API's redirect.
  await context.route("**/api/auth/*/login", async (route) => {
    // The real response, so its OAuth state cookie is still set.
    const login = await route.fetch({ maxRedirects: 0 })
    const location = approval(login.headers()["location"] ?? "")

    if (location === null) {
      return route.fallback()
    }

    return route.fulfill({
      response: login,
      headers: { ...login.headers(), location },
    })
  })

  // Linking and reauthenticating: the SPA navigates to the provider itself.
  await context.route(
    (url) => url.hostname in PROVIDER_BY_HOST,
    (route) => {
      const location = approval(route.request().url())

      return location === null
        ? route.fallback()
        : route.fulfill({ status: 302, headers: { location } })
    }
  )
}

export async function signInWith(
  page: Page,
  provider: Provider,
  response: ProviderResponse
): Promise<void> {
  await answerProvidersWith(page.context(), { [provider]: response })
  await page.goto("/login")
  await page
    .getByRole("link", { name: `Continue with ${PROVIDER_LABELS[provider]}` })
    .click()
}

export async function signIn(
  page: Page,
  identity: TestIdentity
): Promise<void> {
  await signInWith(page, identity.provider, identity.response)
  await page.waitForURL("/")
}

export const PASSWORD = "a perfectly fine passphrase"

// The link in the last email sent to `to`. Emails go out after the response,
// so wait for it to arrive.
export async function latestEmailLink(page: Page, to: string): Promise<string> {
  let link = ""

  await expect
    .poll(async () => {
      const response = await page.request.get(
        `/api/__e2e__/outbox?to=${encodeURIComponent(to)}`
      )
      link = response.ok() ? (await response.json()).link : ""
      return link
    })
    .not.toBe("")

  return link
}

export interface PasswordUser {
  name: string
  email: string
  password: string
}

export function newPasswordUser(): PasswordUser {
  const id = crypto.randomUUID()

  return {
    name: `Test User ${id.slice(0, 8)}`,
    email: `user-${id}@example.com`,
    password: PASSWORD,
  }
}

// Sign up by email and land signed in.
export async function signUp(page: Page, user: PasswordUser): Promise<void> {
  await page.goto("/signup")
  await page.getByLabel("Email").fill(user.email)
  await page.getByRole("button", { name: "Continue with email" }).click()
  await expect(page.getByText(`Check ${user.email}`)).toBeVisible()

  await page.goto(await latestEmailLink(page, user.email))
  await page.getByLabel("Name").fill(user.name)
  await page.getByLabel("Password").fill(user.password)
  await page.getByRole("button", { name: "Create account" }).click()
  await page.waitForURL("/")
}

import {
  expect,
  newIdentity,
  signIn,
  signInWith,
  test,
  type Provider,
} from "./fixtures"

const PROVIDERS: Provider[] = ["google", "microsoft", "github"]

for (const provider of PROVIDERS) {
  test(`signs in with ${provider}`, async ({ page }) => {
    const identity = newIdentity(provider)

    await signIn(page, identity)

    await expect(
      page.getByRole("heading", { name: `Welcome, ${identity.name}` })
    ).toBeVisible()
    await expect(page.getByText(identity.email)).toBeVisible()
  })
}

test("a returning user lands in the same account", async ({ page }) => {
  const identity = newIdentity("google")
  await signIn(page, identity)
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")

  await signIn(page, identity)

  await expect(
    page.getByRole("heading", { name: `Welcome, ${identity.name}` })
  ).toBeVisible()
})

test("cancelling at the provider returns to sign-in with an error", async ({
  page,
}) => {
  await signInWith(page, "google", { error: "access_denied" })

  await page.waitForURL("/login?error=oauth_failed")
  await expect(page.getByRole("alert")).toContainText(
    "Sign-in was cancelled or didn't complete"
  )
})

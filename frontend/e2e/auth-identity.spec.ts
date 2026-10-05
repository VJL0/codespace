import { expect, newIdentity, signIn, signInWith, test } from "./fixtures"

test("a Microsoft account without an email still signs in", async ({
  page,
}) => {
  const identity = newIdentity("microsoft")
  const claims = { ...(identity.response.claims as Record<string, unknown>) }
  delete claims.email
  delete claims.xms_edov

  await signIn(page, { ...identity, response: { claims } })

  await expect(
    page.getByRole("heading", { name: `Welcome, ${identity.name}` })
  ).toBeVisible()
  await expect(page.getByText(identity.email)).toHaveCount(0)
})

test("another provider with the same verified email isn't merged in", async ({
  page,
}) => {
  const google = newIdentity("google")
  await signIn(page, google)
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")

  const github = newIdentity("github")
  await signInWith(page, "github", {
    ...github.response,
    github_emails: [
      { email: google.email, primary: true, verified: true, visibility: null },
    ],
  })

  await page.waitForURL("/login?error=account_exists")
  await expect(page.getByRole("alert")).toContainText(
    "An account with this email already exists"
  )
})

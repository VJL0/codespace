import type { Page } from "@playwright/test"

import {
  answerProvidersWith,
  expect,
  newIdentity,
  signIn,
  test,
  type TestIdentity,
} from "./fixtures"

function row(page: Page, label: string) {
  return page.getByRole("listitem", { name: label })
}

// Sign in, then confirm it's you with the same account, as the settings
// page asks before any change to sign-in methods.
async function signInAndConfirm(page: Page, identity: TestIdentity) {
  await signIn(page, identity)
  await page.goto("/settings")
  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()
  await page
    .getByRole("button", {
      name: `Continue with ${identity.provider === "google" ? "Google" : "Microsoft"}`,
    })
    .click()
  await expect(page.getByText("Confirmed.")).toBeVisible()
}

test("linking asks to confirm it's you, then adds the account", async ({
  page,
}) => {
  const google = newIdentity("google")
  const github = newIdentity("github")
  await answerProvidersWith(page.context(), { github: github.response })

  // A provider sign-in alone isn't fresh enough to change sign-in methods.
  await signIn(page, google)
  await page.goto("/settings")
  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()
  await expect(
    page.getByRole("heading", { name: "Confirm it's you" })
  ).toBeVisible()
  await page.getByRole("button", { name: "Continue with Google" }).click()
  await expect(page.getByText("Confirmed.")).toBeVisible()

  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()

  await expect(page.getByText("GitHub is now linked.")).toBeVisible()
  await expect(row(page, "GitHub")).toContainText(github.email)
})

test("Microsoft can confirm it's you too", async ({ page }) => {
  await signInAndConfirm(page, newIdentity("microsoft"))
})

test("an account can be unlinked, but not the last one", async ({ page }) => {
  const google = newIdentity("google")
  await answerProvidersWith(page.context(), {
    github: newIdentity("github").response,
  })
  await signInAndConfirm(page, google)
  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()
  await expect(page.getByText("GitHub is now linked.")).toBeVisible()

  await row(page, "GitHub").getByRole("button", { name: "Unlink" }).click()

  await expect(row(page, "GitHub")).toContainText("Not linked")
  await expect(
    row(page, "Google").getByRole("button", { name: "Unlink" })
  ).toBeDisabled()
})

test("an account linked to someone else is refused", async ({
  page,
  browser,
}) => {
  const theirs = newIdentity("github")
  const other = await (await browser.newContext()).newPage()
  await signIn(other, theirs)

  await answerProvidersWith(page.context(), { github: theirs.response })
  await signInAndConfirm(page, newIdentity("google"))
  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()

  await expect(page.getByRole("alert")).toContainText(
    "already linked to a different user"
  )
  await expect(row(page, "GitHub")).toContainText("Not linked")
})

test("a stale confirmation from the provider is rejected", async ({ page }) => {
  // Google answered from an old sign-in instead of asking again.
  const google = newIdentity("google")
  await signIn(page, google)
  const anHourAgo = Math.floor(Date.now() / 1000) - 3600
  await answerProvidersWith(page.context(), {
    google: {
      claims: {
        ...(google.response.claims as object),
        auth_time: anHourAgo,
      },
    },
  })
  await page.goto("/settings")
  await row(page, "GitHub").getByRole("button", { name: "Link" }).click()

  await page.getByRole("button", { name: "Continue with Google" }).click()

  await expect(page.getByRole("alert")).toContainText(
    "We couldn't confirm it's you"
  )
})

test("GitHub can't confirm it's you, but its email can", async ({ page }) => {
  await signIn(page, newIdentity("github"))
  await page.goto("/settings")

  await row(page, "Google").getByRole("button", { name: "Link" }).click()

  await expect(
    page.getByRole("button", { name: "Email me a link" })
  ).toBeVisible()
  await expect(page.getByRole("button", { name: /Continue with/ })).toHaveCount(
    0
  )
})

test("without an email, a GitHub-only user has no way to confirm", async ({
  page,
}) => {
  const github = newIdentity("github")
  await signIn(page, {
    ...github,
    response: { ...github.response, github_emails: [] },
  })
  await page.goto("/settings")

  await row(page, "Google").getByRole("button", { name: "Link" }).click()

  await expect(
    page.getByText("None of your sign-in methods can confirm it's you yet")
  ).toBeVisible()
  await expect(
    page.getByRole("button", { name: "Email me a link" })
  ).toHaveCount(0)
})

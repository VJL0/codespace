import type { Page } from "@playwright/test"

import {
  answerProvidersWith,
  expect,
  latestEmailLink,
  newIdentity,
  newPasswordUser,
  signIn,
  signUp,
  test,
  type PasswordUser,
} from "./fixtures"

async function logOut(page: Page) {
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")
}

async function logIn(page: Page, email: string, password: string) {
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(password)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
}

async function signedUpAndOut(page: Page): Promise<PasswordUser> {
  const user = newPasswordUser()
  await signUp(page, user)
  await logOut(page)

  return user
}

function githubRow(page: Page) {
  return page.getByRole("listitem", { name: "GitHub" })
}

test("signs in with email and password", async ({ page }) => {
  const user = await signedUpAndOut(page)

  await logIn(page, user.email, user.password)

  await page.waitForURL("/")
  await expect(
    page.getByRole("heading", { name: `Welcome, ${user.name}` })
  ).toBeVisible()
  await page.reload()
  await expect(
    page.getByRole("heading", { name: `Welcome, ${user.name}` })
  ).toBeVisible()
})

test("a wrong password gets the same answer as an unknown email", async ({
  page,
}) => {
  const user = await signedUpAndOut(page)

  await logIn(page, user.email, "the wrong passphrase")
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect email or password."
  )

  await logIn(page, "nobody@example.com", user.password)
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect email or password."
  )
})

test("too many failed attempts are slowed down", async ({ page }) => {
  const user = await signedUpAndOut(page)

  for (let attempt = 0; attempt < 10; attempt++) {
    await logIn(page, user.email, "the wrong passphrase")
    await expect(page.getByRole("alert")).toBeVisible()
  }
  await logIn(page, user.email, user.password)

  await expect(page.getByRole("alert")).toContainText("Too many attempts")
})

test("a password confirms it's you before linking", async ({ page }) => {
  // A password user who signs in with Google: not a fresh session.
  const user = newPasswordUser()
  const google = newIdentity("google")
  await answerProvidersWith(page.context(), {
    google: google.response,
    github: newIdentity("github").response,
  })
  await signUp(page, user)
  await page.goto("/settings")
  await page
    .getByRole("listitem", { name: "Google" })
    .getByRole("button", { name: "Link" })
    .click()
  await expect(page.getByText("Google is now linked.")).toBeVisible()
  await page.getByRole("button", { name: "Log out everywhere" }).click()
  await signIn(page, google)

  await page.goto("/settings")
  await githubRow(page).getByRole("button", { name: "Link" }).click()
  const dialog = page.getByRole("dialog")
  await dialog.getByLabel("Password").fill(user.password)
  await dialog.getByRole("button", { name: "Confirm" }).click()

  await expect(page.getByText("Confirmed.")).toBeVisible()
  await githubRow(page).getByRole("button", { name: "Link" }).click()
  await expect(page.getByText("GitHub is now linked.")).toBeVisible()
})

test("an emailed link confirms it's you, in this browser only", async ({
  page,
  browser,
}) => {
  const google = newIdentity("google")
  await answerProvidersWith(page.context(), {
    github: newIdentity("github").response,
  })
  await signIn(page, google)
  await page.goto("/settings")
  await githubRow(page).getByRole("button", { name: "Link" }).click()

  await page.getByRole("button", { name: "Email me a link" }).click()
  await expect(
    page.getByText(`We sent a link to ${google.email}`)
  ).toBeVisible()
  const link = await latestEmailLink(page, google.email)

  // Opened by someone else, signed in elsewhere, it does nothing.
  const other = await (await browser.newContext()).newPage()
  await signIn(other, newIdentity("microsoft"))
  await other.goto(link)
  await expect(other.getByRole("alert")).toContainText("another browser")

  await page.goto(link)
  await page.waitForURL("/settings?reauthenticated=email")
  await expect(page.getByText("Confirmed.")).toBeVisible()
  await githubRow(page).getByRole("button", { name: "Link" }).click()
  await expect(page.getByText("GitHub is now linked.")).toBeVisible()
})

import type { Browser, Page } from "@playwright/test"

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

const NEW_PASSWORD = "an entirely new passphrase"

async function logIn(page: Page, email: string, password: string) {
  await page.goto("/login")
  await page.getByLabel("Email").fill(email)
  await page.getByLabel("Password").fill(password)
  await page.getByRole("button", { name: "Sign in", exact: true }).click()
}

// The same user, signed in with their password in another browser.
async function otherBrowser(browser: Browser, user: PasswordUser) {
  const page = await (await browser.newContext()).newPage()
  await logIn(page, user.email, user.password)
  await page.waitForURL("/")

  return page
}

async function expectSignedOut(page: Page) {
  await page.goto("/")
  await page.waitForURL("/login")
}

test("resetting a forgotten password signs out everywhere", async ({
  page,
  browser,
}) => {
  const user = newPasswordUser()
  await signUp(page, user)
  const laptop = await otherBrowser(browser, user)
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")

  await page.getByRole("link", { name: "Forgot password?" }).click()
  await page.waitForURL("/forgot-password")
  await page.getByLabel("Email").fill(user.email)
  await page.getByRole("button", { name: "Email me a link" }).click()
  await expect(page.getByText("we've sent it a link")).toBeVisible()
  await page.goto(await latestEmailLink(page, user.email))
  await page.getByLabel("New password").fill(NEW_PASSWORD)
  await page.getByRole("button", { name: "Reset password" }).click()
  await expect(page.getByText("Your password is changed")).toBeVisible()

  await expectSignedOut(laptop)
  await logIn(page, user.email, user.password)
  await expect(page.getByRole("alert")).toHaveText(
    "Incorrect email or password."
  )
  await logIn(page, user.email, NEW_PASSWORD)
  await page.waitForURL("/")
})

test("changing the password signs out other browsers", async ({
  page,
  browser,
}) => {
  const user = newPasswordUser()
  await signUp(page, user)
  const laptop = await otherBrowser(browser, user)

  await page.goto("/settings")
  await page.getByLabel("Current password").fill(user.password)
  await page.getByLabel("New password").fill(NEW_PASSWORD)
  await page.getByRole("button", { name: "Change password" }).click()

  await expect(page.getByText("Password changed.")).toBeVisible()
  await expectSignedOut(laptop)
  // This browser stays signed in.
  await page.reload()
  await expect(page.getByRole("heading", { name: "Settings" })).toBeVisible()
})

test("a Google user adds a password and signs in with it", async ({ page }) => {
  const google = newIdentity("google")
  await signIn(page, google)
  await answerProvidersWith(page.context(), { google: google.response })
  await page.goto("/settings")

  await page.getByRole("button", { name: "Add a password" }).click()
  await page.getByRole("button", { name: "Continue with Google" }).click()
  await expect(page.getByText("Confirmed.")).toBeVisible()
  await page.getByRole("button", { name: "Add a password" }).click()
  await expect(
    page.getByText(`We sent a link to ${google.email}`)
  ).toBeVisible()

  await page.goto(await latestEmailLink(page, google.email))
  await page.getByLabel("New password").fill(NEW_PASSWORD)
  await page.getByRole("button", { name: "Add password" }).click()
  await expect(page.getByText("Password added.")).toBeVisible()

  await page.goto("/")
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")
  await logIn(page, google.email, NEW_PASSWORD)
  await page.waitForURL("/")
  await expect(
    page.getByRole("heading", { name: `Welcome, ${google.name}` })
  ).toBeVisible()
})

test("the only sign-in method can't be removed", async ({ page }) => {
  await signUp(page, newPasswordUser())

  await page.goto("/settings")

  await expect(
    page.getByRole("button", { name: "Remove password" })
  ).toBeDisabled()
})

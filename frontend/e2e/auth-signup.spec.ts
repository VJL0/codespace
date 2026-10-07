import {
  expect,
  latestEmailLink,
  newPasswordUser,
  signIn,
  newIdentity,
  signUp,
  test,
} from "./fixtures"

test("signs up by email and lands signed in", async ({ page }) => {
  const user = newPasswordUser()

  await signUp(page, user)

  await expect(
    page.getByRole("heading", { name: `Welcome, ${user.name}` })
  ).toBeVisible()
  await expect(page.getByText(user.email)).toBeVisible()
})

test("a breached password is refused, and the link still works", async ({
  page,
}) => {
  const user = newPasswordUser()
  await page.goto("/signup")
  await page.getByLabel("Email").fill(user.email)
  await page.getByRole("button", { name: "Email me a link" }).click()
  await page.goto(await latestEmailLink(page, user.email))
  await page.getByLabel("Name").fill(user.name)

  await page.getByLabel("Password").fill("correct horse battery staple")
  await page.getByRole("button", { name: "Create account" }).click()
  await expect(page.getByRole("alert")).toContainText("data breach")

  await page.getByLabel("Password").fill(user.password)
  await page.getByRole("button", { name: "Create account" }).click()
  await page.waitForURL("/")
})

test("a sign-up link works once", async ({ page, browser }) => {
  const user = newPasswordUser()
  await signUp(page, user)
  const link = await latestEmailLink(page, user.email)

  const other = await (await browser.newContext()).newPage()
  await other.goto(link)
  await other.getByLabel("Name").fill("Someone")
  await other.getByLabel("Password").fill(user.password)
  await other.getByRole("button", { name: "Create account" }).click()

  await expect(other.getByRole("alert")).toContainText(
    "expired or was already used"
  )
})

test("signing up with a taken address emails its owner instead", async ({
  page,
}) => {
  const identity = newIdentity("google")
  await signIn(page, identity)
  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")

  await page.goto("/signup")
  await page.getByLabel("Email").fill(identity.email)
  await page.getByRole("button", { name: "Email me a link" }).click()

  // The page says the same as for a free address.
  await expect(page.getByText(`Check ${identity.email}`)).toBeVisible()
  expect(await latestEmailLink(page, identity.email)).toMatch(/\/login$/)
})

import { expect, newIdentity, signIn, test } from "./fixtures"

test("the session survives a reload", async ({ page }) => {
  const identity = newIdentity("google")
  await signIn(page, identity)

  await page.reload()

  await expect(
    page.getByRole("heading", { name: `Welcome, ${identity.name}` })
  ).toBeVisible()
})

test("signed-out visitors are sent to sign-in", async ({ page }) => {
  await page.goto("/")

  await page.waitForURL("/login")
})

test("logging out ends the session", async ({ page }) => {
  await signIn(page, newIdentity("github"))

  await page.getByRole("button", { name: "Log out", exact: true }).click()
  await page.waitForURL("/login")

  await page.goto("/")
  await page.waitForURL("/login")
})

test("logging out everywhere signs out other browsers too", async ({
  browser,
}) => {
  const identity = newIdentity("microsoft")
  const laptop = await (await browser.newContext()).newPage()
  const phone = await (await browser.newContext()).newPage()
  await signIn(laptop, identity)
  await signIn(phone, identity)

  await laptop.getByRole("button", { name: "Log out everywhere" }).click()
  await laptop.waitForURL("/login")

  await phone.goto("/")
  await phone.waitForURL("/login")
})

test("a cross-site page can't sign the user out", async ({ page }) => {
  const identity = newIdentity("google")
  await signIn(page, identity)

  // Another site posts to the API, which the browser marks Sec-Fetch-Site:
  // cross-site. 127.0.0.1 is a different site from localhost; it's a real
  // local page because Chrome blocks routed or public pages from reaching
  // local servers at all.
  await page.goto("http://127.0.0.1:5174/")
  const logoutAll = new URL(
    "/api/auth/logout-all",
    test.info().project.use.baseURL
  )
  await page.evaluate(async (url) => {
    await fetch(url, {
      method: "POST",
      mode: "no-cors",
      credentials: "include",
    })
  }, logoutAll.toString())

  await page.goto("/")
  await expect(
    page.getByRole("heading", { name: `Welcome, ${identity.name}` })
  ).toBeVisible()
})

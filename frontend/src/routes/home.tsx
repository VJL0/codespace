import { Link, useLoaderData, useNavigate } from "react-router"
import type { LoaderFunctionArgs } from "react-router"

import { Button, buttonVariants } from "@/components/ui/button"
import { logout, logoutEverywhere } from "@/lib/api"
import { currentUserContext } from "@/lib/current-user-context"

export function loader({ context }: LoaderFunctionArgs) {
  return context.get(currentUserContext)
}

export function Component() {
  const user = useLoaderData<typeof loader>()
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate("/login", { replace: true })
  }

  async function handleLogoutEverywhere() {
    await logoutEverywhere()
    navigate("/login", { replace: true })
  }

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 p-6 text-center">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">
          Welcome{user.name ? `, ${user.name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">{user.email}</p>
      </div>

      <div className="flex gap-2">
        <Link to="/settings" className={buttonVariants({ variant: "outline" })}>
          Settings
        </Link>
        <Button variant="outline" onClick={handleLogout}>
          Log out
        </Button>
        <Button variant="outline" onClick={handleLogoutEverywhere}>
          Log out everywhere
        </Button>
      </div>
    </div>
  )
}

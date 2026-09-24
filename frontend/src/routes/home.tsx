import { useLoaderData, useNavigate } from "react-router"
import type { LoaderFunctionArgs } from "react-router"

import { Button } from "@/components/ui/button"
import { logout } from "@/lib/api"
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

  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-6 p-6 text-center">
      <div className="space-y-1">
        <h1 className="text-xl font-semibold">
          Welcome{user.full_name ? `, ${user.full_name}` : ""}
        </h1>
        <p className="text-sm text-muted-foreground">{user.email}</p>
      </div>

      <Button variant="outline" onClick={handleLogout}>
        Log out
      </Button>
    </div>
  )
}

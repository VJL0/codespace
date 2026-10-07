import { redirect } from "react-router"
import type { MiddlewareFunction } from "react-router"

import { getCurrentUser } from "@/lib/api"
import { currentUserContext } from "@/lib/current-user-context"

export const requireAuth: MiddlewareFunction = async ({ context }) => {
  const user = await getCurrentUser()

  if (user === null) {
    throw redirect("/login")
  }

  context.set(currentUserContext, user)
}

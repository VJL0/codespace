import { createContext } from "react-router"

import type { CurrentUser } from "@/lib/api"

export const currentUserContext = createContext<CurrentUser>()

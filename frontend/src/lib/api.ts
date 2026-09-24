import { API_URL } from "@/lib/config"

export interface CurrentUser {
  public_id: string
  email: string
  full_name: string | null
  avatar_url: string | null
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const response = await fetch(`${API_URL}/api/auth/me`, {
    credentials: "include",
  })

  if (response.status === 401) {
    return null
  }

  if (!response.ok) {
    throw new Error("Failed to load the current user.")
  }

  return response.json()
}

export async function logout(): Promise<void> {
  await fetch(`${API_URL}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
  })
}

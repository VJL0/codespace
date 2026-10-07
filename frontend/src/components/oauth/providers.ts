import type { ComponentType } from "react"

import {
  GitHubLogo,
  GoogleLogo,
  MicrosoftLogo,
} from "@/components/oauth/provider-logos"
import type { OAuthProvider } from "@/lib/api"

export interface OAuthProviderInfo {
  id: OAuthProvider
  label: string
  Logo: ComponentType
}

export const OAUTH_PROVIDERS: OAuthProviderInfo[] = [
  { id: "google", label: "Google", Logo: GoogleLogo },
  { id: "microsoft", label: "Microsoft", Logo: MicrosoftLogo },
  { id: "github", label: "GitHub", Logo: GitHubLogo },
]

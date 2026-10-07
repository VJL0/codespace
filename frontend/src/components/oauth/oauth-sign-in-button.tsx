import { buttonVariants } from "@/components/ui/button"
import type { OAuthProviderInfo } from "@/components/oauth/providers"
import { API_URL } from "@/lib/config"
import { cn } from "@/lib/utils"

interface OAuthSignInButtonProps {
  provider: OAuthProviderInfo
  className?: string
}

export function OAuthSignInButton({
  provider,
  className,
}: OAuthSignInButtonProps) {
  return (
    <a
      href={`${API_URL}/api/auth/${provider.id}/login`}
      className={cn(
        buttonVariants({ variant: "outline", size: "lg" }),
        "gap-3",
        className
      )}
    >
      <provider.Logo />
      Sign in with {provider.label}
    </a>
  )
}

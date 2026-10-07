import { buttonVariants } from "@/components/ui/button"
import type { OAuthProviderInfo } from "@/components/oauth/providers"
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
      href={`/api/auth/${provider.id}/login`}
      className={cn(
        buttonVariants({ variant: "outline", size: "lg" }),
        "gap-3",
        className
      )}
    >
      <provider.Logo />
      Continue with {provider.label}
    </a>
  )
}

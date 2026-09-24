import type { Metadata } from "next";
import type { ReactElement } from "react";

import AuthForm from "@/components/AuthForm";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Sign in",
  robots: { index: false, follow: false },
};

// Set by redirectToLoginAfterSessionExpiry (lib/api.ts, "expired")
// and DeleteAccountModal (lib/api.ts's clearTokens + this page's
// own "deleted" reason) after a real backend response, never
// optimistically. Shown instead of raw backend response text
// ("Invalid refresh token" etc.), which describes what the server
// saw, not what the person should do about it.
const REASON_MESSAGE: Record<string, string> = {
  expired: "Your session expired. Please log in again.",
  deleted: "Your account has been deleted.",
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}): Promise<ReactElement> {
  const { reason } = await searchParams;
  const message = reason ? REASON_MESSAGE[reason] : undefined;

  return (
    <div className="shell">
      <SiteHeader />
      <main>
        <section className="block">
          <div className="wrap">
            <h1 style={{ marginBottom: "1.5rem" }}>Sign in</h1>
            {message && (
              <p
                className="alert alert-quiet"
                role="status"
                style={{ marginBottom: "1.5rem" }}
              >
                {message}
              </p>
            )}
            <AuthForm mode="login" />
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

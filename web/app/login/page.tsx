import type { Metadata } from "next";
import type { ReactElement } from "react";

import AuthForm from "@/components/AuthForm";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Sign in",
  robots: { index: false, follow: false },
};

export default async function LoginPage({
  searchParams,
}: {
  searchParams: Promise<{ reason?: string }>;
}): Promise<ReactElement> {
  // Set by redirectToLoginAfterSessionExpiry (lib/api.ts) whenever
  // an authenticated page's request gets a 401 and the automatic
  // token refresh also fails. Shown instead of the backend's own
  // response text ("Invalid refresh token" etc.), which describes
  // what the server saw, not what the person should do about it.
  const expired = (await searchParams).reason === "expired";

  return (
    <div className="shell">
      <SiteHeader />
      <main>
        <section className="block">
          <div className="wrap">
            <h1 style={{ marginBottom: "1.5rem" }}>Sign in</h1>
            {expired && (
              <p
                className="alert alert-quiet"
                role="status"
                style={{ marginBottom: "1.5rem" }}
              >
                Your session expired. Please log in again.
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

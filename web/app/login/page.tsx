import type { Metadata } from "next";
import type { ReactElement } from "react";

import AuthForm from "@/components/AuthForm";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Sign in",
  robots: { index: false, follow: false },
};

export default function LoginPage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader />
      <main>
        <section className="block">
          <div className="wrap">
            <h1 style={{ marginBottom: "1.5rem" }}>Sign in</h1>
            <AuthForm mode="login" />
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

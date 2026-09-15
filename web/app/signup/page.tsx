import type { Metadata } from "next";
import type { ReactElement } from "react";

import AuthForm from "@/components/AuthForm";
import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Create an account",
  robots: { index: false, follow: false },
};

export default function SignupPage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader />
      <main>
        <section className="block">
          <div className="wrap">
            <h1 style={{ marginBottom: "0.75rem" }}>Create an account</h1>
            <p className="lede" style={{ marginBottom: "1.75rem" }}>
              You need one to record a session, because your recordings
              and feedback are stored against it.
            </p>
            <AuthForm mode="signup" />
          </div>
        </section>
      </main>
      <SiteFooter />
    </div>
  );
}

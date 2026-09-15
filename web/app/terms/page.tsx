import type { Metadata } from "next";
import Link from "next/link";
import type { ReactElement } from "react";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Terms",
  description:
    "The terms you agree to when using Debate Coach, including acceptable use, ownership of recordings, and limits of the service.",
};

const UPDATED = "15 September 2026";

export default function TermsPage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader />

      <main>
        <section className="block">
          <div className="wrap prose">
            <h1 style={{ fontSize: "var(--step-4)" }}>
              Terms of service
            </h1>
            <p className="note">Last updated {UPDATED}</p>

            <p>
              These terms are an agreement between you and{" "}
              <strong>[LEGAL ENTITY NAME]</strong> covering your use of
              Debate Coach. Creating an account means you accept them. If
              you do not, do not use the service.
            </p>

            <h2>Who can use it</h2>
            <p>
              You must be at least 13 years old. If you are under 18, a
              parent or guardian must agree to these terms on your behalf.
              You are responsible for keeping your password to yourself
              and for everything done through your account.
            </p>

            <h2>What you may record</h2>
            <p>You may upload a recording only if:</p>
            <ul>
              <li>it is your own speech, or</li>
              <li>
                everyone whose voice appears in it has agreed to it being
                recorded and analysed.
              </li>
            </ul>
            <p>
              Do not upload recordings of people who have not agreed,
              recordings of confidential proceedings, or anything you do
              not have the right to share. Do not use the service to
              harass anyone, to break the law, or to try to reach parts of
              the system you have not been given access to.
            </p>

            <h2>Your recordings stay yours</h2>
            <p>
              You keep all rights to your recordings and to their
              transcripts. You give us permission to store them and to
              pass them to the processors listed in the{" "}
              <Link href="/privacy">privacy policy</Link> for the sole
              purpose of producing your analysis. We do not use your
              recordings to train models, and we do not license them to
              anyone.
            </p>

            <h2>What the service is, and is not</h2>
            <p>
              Debate Coach measures your delivery and offers an
              interpretation of your argument. The delivery figures are
              arithmetic over your audio and are reliable in the ordinary
              sense. The reading of your argument is produced by a
              language model and can be wrong, incomplete or confidently
              mistaken.
            </p>
            <p>
              The feedback is a practice aid. It is not coaching from a
              qualified person, not an assessment of competitive merit,
              and not advice of any professional kind. Do not rely on it
              as the only input to a decision that matters to you.
            </p>

            <h2>Availability</h2>
            <p>
              We do not promise the service will be available at all
              times. Analysis depends on third-party providers whose
              capacity we do not control, so a session may be queued or
              may fail. We may change, suspend or withdraw features, and
              we will give notice of significant changes where we can.
            </p>

            <h2>Accounts we may close</h2>
            <p>
              We may suspend or close an account that breaks these terms,
              that places an unreasonable load on the service, or that we
              are legally required to close. Where the circumstances
              allow, we will tell you first and give you a chance to
              export your sessions.
            </p>

            <h2>Ending your use</h2>
            <p>
              You may stop using Debate Coach and ask us to close your
              account at any time. Closing it deletes your sessions, which
              cannot be undone.
            </p>

            <h2>Liability</h2>
            <p>
              To the fullest extent the law allows, the service is
              provided as it is, without warranties of any kind, and we
              are not liable for indirect or consequential loss, lost
              opportunities, or competitive outcomes arising from your use
              of it. Nothing here limits liability that cannot be limited
              by law.
            </p>

            <h2>Governing law</h2>
            <p>
              These terms are governed by the laws of{" "}
              <strong>[JURISDICTION]</strong>, and its courts have
              exclusive jurisdiction over any dispute arising from them.
            </p>

            <h2>Changes</h2>
            <p>
              We may update these terms. The date at the top shows when
              they last changed, and we will tell you by email before a
              change that materially affects your rights takes effect.
            </p>

            <h2>Contact</h2>
            <p>
              Write to{" "}
              <a href="mailto:support@yourdomain.com">
                support@yourdomain.com
              </a>
              .
            </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

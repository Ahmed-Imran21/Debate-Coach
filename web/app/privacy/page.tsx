import type { Metadata } from "next";
import Link from "next/link";
import type { ReactElement } from "react";

import SiteFooter from "@/components/SiteFooter";
import SiteHeader from "@/components/SiteHeader";

export const metadata: Metadata = {
  title: "Privacy",
  description:
    "What Debate Coach collects, where recordings are stored, which third parties process them, and how to delete your data.",
};

const UPDATED = "15 September 2026";

export default function PrivacyPage(): ReactElement {
  return (
    <div className="shell">
      <SiteHeader />

      <main>
        <section className="block">
          <div className="wrap prose">
            <h1 style={{ fontSize: "var(--step-4)" }}>Privacy policy</h1>
            <p className="note">Last updated {UPDATED}</p>

            <p>
              This policy covers Debate Coach, operated by{" "}
              <strong>[LEGAL ENTITY NAME]</strong> of{" "}
              <strong>[REGISTERED ADDRESS]</strong>. It describes what the
              service collects, where it goes, and how to get rid of it.
            </p>

            <h2>What we collect</h2>

            <h3>Account details</h3>
            <p>
              Your first name, last name and email address, and a hash of
              your password. We never store the password itself. The email
              address is used to identify your account and to contact you
              about the service.
            </p>

            <h3>Recordings</h3>
            <p>
              The audio you record or upload. A recording is stored so
              that you can play it back alongside its analysis.
            </p>

            <h3>Analysis output</h3>
            <p>
              The transcript of your recording, the delivery metrics
              derived from it, the labelled breakdown of your argument,
              and the coaching feedback produced from those. Each of these
              is stored against your account.
            </p>

            <h3>Technical logs</h3>
            <p>
              Our servers record request times, response codes and IP
              addresses to operate the service and to enforce rate limits.
              These logs are not used to build a profile of you and are
              retained for no longer than 30 days.
            </p>

            <h3>What we do not collect</h3>
            <p>
              There is no advertising on Debate Coach and no third-party
              analytics or tracking. We set no cookies for tracking. Web
              fonts are served from our own domain, so no font provider
              sees your IP address. Your authentication token is kept in
              your browser&rsquo;s local storage and is sent only to our
              own API.
            </p>

            <h2>Who else processes your data</h2>

            <p>
              Analysing a speech means sending it to services we do not
              run. This is the complete list.
            </p>

            <h3>Groq</h3>
            <p>
              Your audio is sent to Groq for transcription, and your
              transcript is sent to Groq for argument analysis and
              coaching feedback. Groq therefore processes the content of
              your recordings.
            </p>

            <h3>Google (Gemini)</h3>
            <p>
              Where Groq is unavailable, transcript text may instead be
              sent to Google&rsquo;s Gemini API for the same analysis
              steps. Google therefore may process the text of your
              recordings, though not the audio.
            </p>

            <h3>Object storage and hosting</h3>
            <p>
              Recordings and analysis files are held in an S3-compatible
              object store operated by{" "}
              <strong>[STORAGE PROVIDER]</strong> in{" "}
              <strong>[REGION]</strong>. The application itself runs on{" "}
              <strong>[HOSTING PROVIDER]</strong>. The storage bucket is
              private; files are reachable only through short-lived links
              issued by our API to your signed-in session.
            </p>

            <p>
              We do not sell your data, and we do not share it with anyone
              beyond the processors named above except where the law
              requires it.
            </p>

            <h2>Where your data is held</h2>
            <p>
              Recordings and analysis are stored in{" "}
              <strong>[REGION]</strong>. The processors above may handle
              your data in other countries, including the United States.
            </p>

            <h2>How long we keep it</h2>
            <p>
              Recordings and their analysis are kept until you delete
              them or close your account. Deleting a session removes its
              audio and every analysis file from storage. Closing your
              account removes your account record and every session
              attached to it. Backups are overwritten within 30 days.
            </p>

            <h2>Your choices</h2>
            <ul>
              <li>
                Delete any single session from the practice page. This is
                immediate and cannot be undone.
              </li>
              <li>
                Request a copy of everything held against your account by
                writing to the address below.
              </li>
              <li>
                Ask us to correct your name or email address, or to close
                your account entirely.
              </li>
            </ul>

            <p>
              Depending on where you live, you may have further rights
              over your data, including the right to object to processing
              and to complain to a data protection regulator.
            </p>

            <h2>Children</h2>
            <p>
              Debate Coach is not intended for children under 13, and we
              do not knowingly create accounts for them. School and
              university debaters under 18 should have a parent or
              guardian agree to these terms first. If you believe a child
              has created an account, write to us and we will remove it.
            </p>

            <h2>Security</h2>
            <p>
              Traffic is encrypted in transit. Passwords are stored as
              bcrypt hashes. Storage is private and reachable only through
              expiring links. No system is perfectly secure, and we will
              tell affected users without undue delay if a breach puts
              their data at risk.
            </p>

            <h2>Changes</h2>
            <p>
              If this policy changes in a way that affects how your data
              is used, we will say so on this page and, for significant
              changes, by email.
            </p>

            <h2>Contact</h2>
            <p>
              Write to{" "}
              <a href="mailto:privacy@yourdomain.com">
                privacy@yourdomain.com
              </a>{" "}
              with anything about this policy, or to exercise any of the
              rights above.
            </p>

            <p className="note">
              See also the <Link href="/terms">terms of service</Link>.
            </p>
          </div>
        </section>
      </main>

      <SiteFooter />
    </div>
  );
}

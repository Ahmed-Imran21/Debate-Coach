"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useRef, useState, type FormEvent, type ReactElement, type RefObject } from "react";

import { ApiError, login, signup } from "@/lib/api";
import {
  CONSENT_LINE_PREFIX,
  CONSENT_REQUIRED_MESSAGE,
  LEGAL_LINKS,
  NO_CONSENT,
  canCreateAccount,
  consentFields,
  type SignupConsent,
} from "@/lib/signup-consent";

interface Props {
  mode: "login" | "signup";
}

export default function AuthForm({ mode }: Props): ReactElement {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [consent, setConsent] = useState<SignupConsent>(NO_CONSENT);
  const privacyBox = useRef<HTMLInputElement>(null);
  const termsBox = useRef<HTMLInputElement>(null);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";
  const consentMissing = isSignup && !canCreateAccount(consent);

  function tick(key: keyof SignupConsent, checked: boolean): void {
    const next = { ...consent, [key]: checked };
    setConsent(next);
    if (canCreateAccount(next) && error === CONSENT_REQUIRED_MESSAGE) setError(null);
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);

    if (isSignup && password.length < 8) {
      setError("Use a password of at least 8 characters.");
      return;
    }

    // The button only looks disabled (aria-disabled), so a click or
    // Enter still lands here and can say why.
    if (consentMissing) {
      setError(CONSENT_REQUIRED_MESSAGE);
      (consent.privacyPolicy ? termsBox : privacyBox).current?.focus();
      return;
    }

    setBusy(true);

    try {
      if (isSignup) {
        await signup({
          email,
          password,
          first_name: firstName,
          last_name: lastName,
          ...consentFields(consent),
        });
      } else {
        await login({ email, password });
      }

      router.replace("/practice");
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : "Could not reach the server. Check your connection and try again.",
      );
      setBusy(false);
    }
  }

  return (
    <form className="form-panel" onSubmit={handleSubmit} noValidate>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {isSignup && (
        <>
          <label className="field">
            <span>First name</span>
            <input
              type="text"
              name="given-name"
              autoComplete="given-name"
              required
              value={firstName}
              onChange={(event) => setFirstName(event.target.value)}
            />
          </label>

          <label className="field">
            <span>Last name</span>
            <input
              type="text"
              name="family-name"
              autoComplete="family-name"
              required
              value={lastName}
              onChange={(event) => setLastName(event.target.value)}
            />
          </label>
        </>
      )}

      <label className="field">
        <span>Email</span>
        <input
          type="email"
          name="email"
          autoComplete="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
      </label>

      <label className="field">
        <span>Password</span>
        <input
          type="password"
          name="password"
          autoComplete={isSignup ? "new-password" : "current-password"}
          required
          minLength={isSignup ? 8 : undefined}
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
      </label>

      {isSignup && (
        <div className="consent-group" role="group" aria-label="Agreements">
          <ConsentLine
            inputRef={privacyBox}
            link={LEGAL_LINKS.privacyPolicy}
            checked={consent.privacyPolicy}
            onChange={(checked) => tick("privacyPolicy", checked)}
          />
          <ConsentLine
            inputRef={termsBox}
            link={LEGAL_LINKS.terms}
            checked={consent.terms}
            onChange={(checked) => tick("terms", checked)}
          />
        </div>
      )}

      <button
        className="btn"
        type="submit"
        disabled={busy}
        aria-disabled={consentMissing || undefined}
      >
        {busy
          ? isSignup
            ? "Creating account"
            : "Signing in"
          : isSignup
            ? "Create account"
            : "Sign in"}
      </button>

      <p className="note" style={{ margin: "1.25rem 0 0" }}>
        {isSignup ? (
          <>
            Already have an account? <Link href="/login">Sign in</Link>.
          </>
        ) : (
          <>
            No account yet? <Link href="/signup">Create one</Link>.
          </>
        )}
      </p>
    </form>
  );
}

/**
 * One sign-up checkbox. The whole line is its label, so tapping the
 * text ticks it; the link inside is interactive content, which a label
 * doesn't activate its control for, so tapping it only opens the page
 * (in a new tab, keeping the form as it is).
 */
function ConsentLine({
  inputRef,
  link,
  checked,
  onChange,
}: {
  inputRef: RefObject<HTMLInputElement | null>;
  link: { href: string; label: string };
  checked: boolean;
  onChange: (checked: boolean) => void;
}): ReactElement {
  return (
    <label className="consent">
      <input
        ref={inputRef}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      <span>
        {CONSENT_LINE_PREFIX}
        <a href={link.href} target="_blank" rel="noopener noreferrer">
          {link.label}
        </a>
      </span>
    </label>
  );
}

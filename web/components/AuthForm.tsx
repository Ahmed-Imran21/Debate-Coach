"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent, type ReactElement } from "react";

import { ApiError, login, signup } from "@/lib/api";

interface Props {
  mode: "login" | "signup";
}

export default function AuthForm({ mode }: Props): ReactElement {
  const router = useRouter();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const isSignup = mode === "signup";

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);

    if (isSignup && password.length < 8) {
      setError("Use a password of at least 8 characters.");
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

      <button className="btn" type="submit" disabled={busy}>
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
            Already have an account? <Link href="/login">Sign in</Link>. By
            creating one you agree to the{" "}
            <Link href="/terms">terms</Link> and{" "}
            <Link href="/privacy">privacy policy</Link>.
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

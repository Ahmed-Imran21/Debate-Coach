"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactElement } from "react";

import {
  ApiError,
  clearTokens,
  deleteAccount,
  redirectToLoginAfterSessionExpiry,
} from "@/lib/api";

const CONFIRM_WORD = "DELETE";

interface Props {
  open: boolean;
  onClose: () => void;
}

/**
 * Typing "DELETE" is a UI confirmation only — it never reaches the
 * backend. The password field is the real re-authentication;
 * app/routes/users.py verifies it server-side against the stored
 * hash before deleting anything. The success/failure message shown
 * here only ever reflects what the backend actually returned —
 * nothing here assumes success before that response arrives.
 */
export default function DeleteAccountModal({ open, onClose }: Props): ReactElement {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);

  const [confirmText, setConfirmText] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) {
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open]);

  function reset(): void {
    setConfirmText("");
    setPassword("");
    setError(null);
    setBusy(false);
  }

  function handleClose(): void {
    if (busy) return;
    reset();
    onClose();
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    setError(null);
    setBusy(true);

    try {
      await deleteAccount(password);
      // The backend has confirmed the account no longer exists —
      // only now is it safe to say so and leave. Reuses the same
      // query-param banner mechanism as the session-expiry
      // redirect (app/login/page.tsx), with its own "deleted"
      // reason, rather than a client-only toast that could vanish
      // before this navigation finishes.
      clearTokens();
      router.replace("/login?reason=deleted");
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        if (caught.message === "Incorrect password.") {
          setError("Incorrect password.");
          setBusy(false);
          return;
        }
        // Any other 401 here means the session itself died (the
        // access token expired and the automatic refresh also
        // failed), not that the password was wrong — that's a
        // different, unrelated failure and gets the same
        // session-expired redirect every other page uses.
        redirectToLoginAfterSessionExpiry(router);
        return;
      }

      setError("Could not delete your account. Try again.");
      setBusy(false);
    }
  }

  const canSubmit = confirmText === CONFIRM_WORD && password.length > 0 && !busy;

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      onClose={handleClose}
      onCancel={handleClose}
    >
      <form className="form-panel" onSubmit={handleSubmit} noValidate>
        <h2 style={{ marginBottom: "0.5rem" }}>Delete your account</h2>
        <p className="note" style={{ marginBottom: "1.25rem" }}>
          This permanently deletes your account, every recorded session and
          every report. This cannot be undone.
        </p>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <label className="field">
          <span>
            Type <strong>{CONFIRM_WORD}</strong> to confirm
          </span>
          <input
            type="text"
            autoComplete="off"
            value={confirmText}
            onChange={(event) => setConfirmText(event.target.value)}
            disabled={busy}
          />
        </label>

        <label className="field">
          <span>Current password</span>
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            disabled={busy}
          />
        </label>

        <div className="btn-row" style={{ marginTop: "1.25rem" }}>
          <button
            type="button"
            className="btn btn-quiet"
            onClick={handleClose}
            disabled={busy}
          >
            Cancel
          </button>
          <button type="submit" className="btn btn-stop" disabled={!canSubmit}>
            {busy ? "Deleting." : "Delete account permanently"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

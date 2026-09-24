"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent, type ReactElement } from "react";

import { ApiError, redirectToLoginAfterSessionExpiry } from "@/lib/api";
import type { AdminUser } from "@/lib/types";

import { deleteUser } from "../admin-api";
import { canConfirmDelete, deleteButtonEnabled } from "./logic";

interface Props {
  /** The user to delete; the dialog is open while this is set. */
  user: AdminUser | null;
  onClose: () => void;
  /** Called only after the backend confirms the account is gone. */
  onDeleted: (user: AdminUser) => void;
}

/**
 * Same shape as components/DeleteAccountModal.tsx, but the typed
 * confirmation is the target's exact email, and there's no password:
 * the admin's own session is the authorization, checked server-side
 * (DELETE /v1/admin/users/{id}). Nothing here reports success before
 * that call has returned.
 */
export default function DeleteUserModal({ user, onClose, onDeleted }: Props): ReactElement {
  const router = useRouter();
  const dialogRef = useRef<HTMLDialogElement>(null);
  // State updates land after a render; this blocks a second submit
  // that arrives before the disabled button has re-rendered.
  const inFlight = useRef(false);

  const [typed, setTyped] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (user && !dialog.open) {
      setTyped("");
      setError(null);
      dialog.showModal();
    } else if (!user && dialog.open) {
      dialog.close();
    }
  }, [user]);

  function handleClose(): void {
    if (inFlight.current) return;
    onClose();
  }

  async function handleSubmit(event: FormEvent): Promise<void> {
    event.preventDefault();
    if (!user || inFlight.current || !canConfirmDelete(typed, user.email)) return;

    inFlight.current = true;
    setBusy(true);
    setError(null);

    try {
      await deleteUser(user.id);
      inFlight.current = false;
      setBusy(false);
      onDeleted(user);
    } catch (caught) {
      inFlight.current = false;
      setBusy(false);

      if (caught instanceof ApiError) {
        if (caught.status === 401) {
          redirectToLoginAfterSessionExpiry(router);
          return;
        }
        if (caught.status === 404) {
          setError("This user no longer exists. They may have deleted their own account.");
          return;
        }
        if (caught.status === 409) {
          // The backend's own explanation: the caller's own account,
          // another admin, or an analysis still running.
          setError(caught.message);
          return;
        }
      }
      setError("Could not delete this user. Try again.");
    }
  }

  const canSubmit = deleteButtonEnabled(typed, user?.email, busy);

  return (
    <dialog
      ref={dialogRef}
      className="confirm-dialog"
      onClose={handleClose}
      onCancel={(event) => {
        // Escape closes a <dialog> natively; not while a delete is in flight.
        if (inFlight.current) event.preventDefault();
      }}
    >
      <form className="form-panel" onSubmit={handleSubmit} noValidate>
        <h2 style={{ marginBottom: "0.5rem" }}>Delete this user</h2>
        <p className="note" style={{ marginBottom: "1.25rem" }}>
          This permanently deletes {user?.email}&apos;s account, every recorded
          session and every report. This cannot be undone.
        </p>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        <label className="field">
          <span>
            Type <strong>{user?.email}</strong> to confirm
          </span>
          <input
            id="confirm-delete-email"
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            disabled={busy}
          />
        </label>

        <div className="btn-row" style={{ marginTop: "1.25rem" }}>
          <button type="button" className="btn btn-quiet" onClick={handleClose} disabled={busy}>
            Cancel
          </button>
          <button type="submit" className="btn btn-stop" disabled={!canSubmit}>
            {busy ? "Deleting." : "Delete user permanently"}
          </button>
        </div>
      </form>
    </dialog>
  );
}

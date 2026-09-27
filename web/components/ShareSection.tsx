"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { ReactElement } from "react";

import {
  ApiError,
  createShareLink,
  getShareStatus,
  redirectToLoginAfterSessionExpiry,
  stopSharing,
} from "@/lib/api";
import { shareUrl } from "@/lib/share";

type State =
  | { kind: "loading" }
  | { kind: "private" }
  // The link is only known right after it's created: the server
  // stores just a hash of the token, so it can't be shown again later.
  | { kind: "shared"; link: string | null };

const COPIED_MS = 2000;

/**
 * The owner's share controls on the report page. Off by default;
 * "Create new link" replaces the link and "Stop sharing" revokes it,
 * and in both cases the old link stops working immediately
 * (app/services/shares.py).
 */
export default function ShareSection({ sessionId }: { sessionId: string }): ReactElement {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const copiedTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let current = true;
    getShareStatus(sessionId)
      .then((status) => {
        if (current) setState(status.sharing ? { kind: "shared", link: null } : { kind: "private" });
      })
      .catch((caught: unknown) => {
        if (!current) return;
        if (caught instanceof ApiError && caught.status === 401) {
          redirectToLoginAfterSessionExpiry(router);
          return;
        }
        setError("Could not load the sharing settings.");
        setState({ kind: "private" });
      });
    return () => {
      current = false;
      if (copiedTimer.current !== null) clearTimeout(copiedTimer.current);
    };
  }, [sessionId, router]);

  async function run(action: () => Promise<void>, failure: string): Promise<void> {
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (caught) {
      if (caught instanceof ApiError && caught.status === 401) {
        redirectToLoginAfterSessionExpiry(router);
        return;
      }
      setError(caught instanceof ApiError ? caught.message : failure);
    } finally {
      setBusy(false);
    }
  }

  function create(): Promise<void> {
    return run(async () => {
      const created = await createShareLink(sessionId);
      setCopied(false);
      setState({ kind: "shared", link: shareUrl(window.location.origin, created.token) });
    }, "Could not create a share link. Try again.");
  }

  function stop(): Promise<void> {
    return run(async () => {
      await stopSharing(sessionId);
      setCopied(false);
      setState({ kind: "private" });
    }, "Could not stop sharing. Try again.");
  }

  async function copy(link: string): Promise<void> {
    try {
      await navigator.clipboard.writeText(link);
    } catch {
      // No clipboard permission (or an old browser): select the text
      // so the user can copy it themselves.
      inputRef.current?.select();
      return;
    }
    setCopied(true);
    if (copiedTimer.current !== null) clearTimeout(copiedTimer.current);
    copiedTimer.current = setTimeout(() => setCopied(false), COPIED_MS);
  }

  return (
    <section data-print="hide" style={{ marginBottom: "2.5rem", maxWidth: "34rem" }}>
      <h2 style={{ fontSize: "var(--step-2)", marginBottom: "0.75rem" }}>Share</h2>

      {state.kind === "loading" && <p className="note">Loading.</p>}

      {state.kind === "private" && (
        <>
          <p className="note">Only you can see this report.</p>
          <div className="btn-row">
            <button className="btn btn-sm" type="button" onClick={() => void create()} disabled={busy}>
              Create share link
            </button>
          </div>
        </>
      )}

      {state.kind === "shared" && (
        <>
          {state.link ? (
            <>
              <label className="field">
                <span>Anyone with this link can view this report</span>
                <input ref={inputRef} type="text" readOnly value={state.link} onFocus={(event) => event.target.select()} />
              </label>
              <div className="btn-row">
                <button className="btn btn-sm" type="button" onClick={() => void copy(state.link as string)} disabled={busy}>
                  {copied ? "Copied" : "Copy link"}
                </button>
                <button className="btn btn-quiet btn-sm" type="button" onClick={() => void create()} disabled={busy}>
                  Create new link
                </button>
                <button className="btn btn-quiet btn-sm" type="button" data-tone="danger" onClick={() => void stop()} disabled={busy}>
                  Stop sharing
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="note">
                Sharing is on. For security, a link is only shown when it&apos;s created. To copy it again,
                create a new link; the current one will stop working.
              </p>
              <div className="btn-row">
                <button className="btn btn-sm" type="button" onClick={() => void create()} disabled={busy}>
                  Create new link
                </button>
                <button className="btn btn-quiet btn-sm" type="button" data-tone="danger" onClick={() => void stop()} disabled={busy}>
                  Stop sharing
                </button>
              </div>
            </>
          )}
          <p className="note" style={{ marginTop: "0.5rem" }}>
            Creating a new link or stopping sharing turns the old link off straight away.
          </p>
        </>
      )}

      {error && (
        <p className="alert alert-quiet" role="status" style={{ marginTop: "0.75rem" }}>
          {error}
        </p>
      )}
    </section>
  );
}

/**
 * The heartbeat's schedule, free of React so vitest can test it with
 * fake timers. components/Heartbeat.tsx wires it to the real API.
 *
 * - A tick only sends while the stored access token is present and
 *   not past its exp. A dead token is never sent every minute.
 * - A 401 from the heartbeat stops it for good (this page load). The
 *   heartbeat never refreshes a session (heartbeat() in api.ts sends
 *   retryOnAuthFailure: false); the next real user action handles an
 *   expired session, as before.
 * - It only starts if the token is live once the page's session sync
 *   has finished.
 */

import { tokenExpiresAt } from "./jwt";

export const HEARTBEAT_INTERVAL_MS = 60_000;

/** A token worth sending: present, readable, and not yet expired. */
export function isLive(token: string | null, now: number = Date.now()): boolean {
  if (!token) return false;
  const expiresAt = tokenExpiresAt(token);
  return expiresAt !== null && expiresAt > now;
}

export interface HeartbeatDeps {
  getToken: () => string | null;
  /** Sends one heartbeat; rejects with an error carrying `status` on failure. */
  send: () => Promise<void>;
  now?: () => number;
  setInterval?: (fn: () => void, ms: number) => ReturnType<typeof setInterval>;
  clearInterval?: (id: ReturnType<typeof setInterval>) => void;
}

export interface Heartbeat {
  /** Call once the page's session sync is done. */
  start: () => void;
  stop: () => void;
  readonly running: boolean;
}

export function createHeartbeat(deps: HeartbeatDeps): Heartbeat {
  const now = deps.now ?? Date.now;
  const set = deps.setInterval ?? ((fn, ms) => setInterval(fn, ms));
  const clear = deps.clearInterval ?? ((id) => clearInterval(id));
  let id: ReturnType<typeof setInterval> | null = null;
  let stopped = false;

  function stop(): void {
    stopped = true;
    if (id !== null) clear(id);
    id = null;
  }

  function tick(): void {
    if (stopped || !isLive(deps.getToken(), now())) return;
    deps.send().catch((error: unknown) => {
      if ((error as { status?: number } | null)?.status === 401) stop();
    });
  }

  return {
    start() {
      if (stopped || id !== null || !isLive(deps.getToken(), now())) return;
      tick();
      id = set(tick, HEARTBEAT_INTERVAL_MS);
    },
    stop,
    get running() {
      return id !== null;
    },
  };
}

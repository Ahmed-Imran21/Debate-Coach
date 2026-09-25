import { tokenExpiresAt } from "./jwt";
import type {
  ProgressMetric,
  ProgressPoint,
  ProgressRange,
  SessionCreated,
  SessionReport,
  SessionSummary,
  Tokens,
  User,
} from "./types";

const BASE = (
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
).replace(/\/$/, "");

const ACCESS_KEY = "dc.access";
const REFRESH_KEY = "dc.refresh";

// Ordinary JSON round trips (list sessions, get a report, log in).
// Generous for a slow connection, short enough that a genuinely
// stalled request doesn't leave a page hanging indefinitely with
// no feedback — previously nothing here had any timeout at all,
// so a stalled (not failed) connection just hung the fetch()
// forever.
const DEFAULT_TIMEOUT_MS = 30_000;

// The audio blob PUT specifically (uploadAndStart, and Recorder.tsx's
// video-analysis path via putToSignedUrl below) goes straight to a
// GCS signed URL, never through request(). A real debate-practice
// recording (opus-compressed speech) is a few MB even for several
// minutes; the 100 MB server-side cap (app/core/config.py
// max_upload_mb) is a safety ceiling, not a realistic size. This is
// generous enough to never abort a real transfer still in progress
// on a slow connection, while still eventually giving up and
// reporting a stall instead of leaving "Sending" on screen forever.
const UPLOAD_TIMEOUT_MS = 10 * 60_000;

/** AbortSignal.timeout ships in every browser this app already
 * requires (Recorder.tsx's own MediaRecorder check), but falls back
 * to no signal rather than throwing if it's ever missing. */
function timeoutSignal(ms: number): AbortSignal | undefined {
  return typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function"
    ? AbortSignal.timeout(ms)
    : undefined;
}

function isTimeout(error: unknown): boolean {
  return error instanceof DOMException && error.name === "TimeoutError";
}

/**
 * Tokens live in localStorage.
 *
 * Known trade-off: localStorage is readable by any script that
 * runs on the page, so a cross-site scripting hole would expose
 * the refresh token. The Content-Security-Policy in
 * next.config.mjs blocks inline and third-party scripts, which
 * is what makes this acceptable for now. Moving refresh tokens
 * to an httpOnly cookie is the stronger answer and needs a
 * matching change on the API.
 */

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

function getRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

/**
 * Every token change in the app goes through storeTokens() or
 * clearTokens() — login, signup and refresh store; sign-out, session
 * expiry, a failed refresh and account deletion clear. Both keep the
 * first-party gate cookie (app/api/session/route.ts) in step, so no
 * individual call site can forget to.
 */
export function storeTokens(tokens: Tokens): Promise<void> {
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
  return syncServerSession(tokens.access_token).then(() => undefined);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
  sessionSync = null;
  forgetSync();
  // keepalive: callers navigate away immediately after this.
  void fetch("/api/session", { method: "DELETE", keepalive: true }).catch(() => {});
}

/* ---------------------------------------------------------- */
/* Server session (first-party gate cookie)                    */
/* ---------------------------------------------------------- */

export interface AdminLink {
  href: string;
  label: string;
}

interface SessionInfo {
  adminLink?: AdminLink;
}

const SYNC_KEY = "dc.session-sync";

let sessionSync: { token: string; promise: Promise<SessionInfo> } | null = null;

// A token's signature is unique to it; enough to key the memo on
// without keeping a second copy of the whole token around.
function tokenKey(token: string): string {
  return token.slice(-24);
}

// Remembered per tab across reloads, so a signed-in visitor syncs
// once per access token (hourly), not once per page load.
function recallSync(token: string): SessionInfo | null {
  try {
    const stored = JSON.parse(window.sessionStorage.getItem(SYNC_KEY) ?? "null");
    return stored?.key === tokenKey(token) ? (stored.info as SessionInfo) : null;
  } catch {
    return null;
  }
}

function rememberSync(token: string, info: SessionInfo): void {
  try {
    window.sessionStorage.setItem(SYNC_KEY, JSON.stringify({ key: tokenKey(token), info }));
  } catch {
    // Storage unavailable: the next page load just syncs again.
  }
}

function forgetSync(): void {
  try {
    window.sessionStorage.removeItem(SYNC_KEY);
  } catch {
    // Nothing to forget.
  }
}

function syncServerSession(accessToken: string): Promise<SessionInfo> {
  const promise: Promise<SessionInfo> = fetch("/api/session", {
    method: "POST",
    headers: { Authorization: `Bearer ${accessToken}` },
    signal: timeoutSignal(DEFAULT_TIMEOUT_MS),
  })
    .then((response) => (response.ok ? response.json() : {}))
    .catch(() => ({}))
    .then((info: SessionInfo) => {
      rememberSync(accessToken, info);
      return info;
    });

  sessionSync = { token: accessToken, promise };
  return promise;
}

/**
 * Called on every page load (components/Heartbeat.tsx) to cover a
 * session that predates this tab — signed in before this code
 * shipped, or whose cookie expired with its access token. Safe to
 * call repeatedly: concurrent callers share one request, and a token
 * that was already synced in this tab isn't synced again.
 */
export function ensureServerSession(): Promise<SessionInfo> {
  const token = getAccessToken();
  if (!token) return Promise.resolve({});

  if (sessionSync?.token === token) return sessionSync.promise;

  const remembered = recallSync(token);
  if (remembered) {
    sessionSync = { token, promise: Promise.resolve(remembered) };
    return sessionSync.promise;
  }

  const expiresAt = tokenExpiresAt(token);
  if (expiresAt !== null && expiresAt <= Date.now()) {
    // Refresh first; its storeTokens() syncs the new token. Keyed on
    // the old token so a second caller shares this, not a 2nd refresh.
    const promise = refreshTokens().then((): Promise<SessionInfo> | SessionInfo => {
      const fresh = getAccessToken();
      return fresh && sessionSync?.token === fresh ? sessionSync.promise : {};
    });
    sessionSync = { token, promise };
    return promise;
  }

  return syncServerSession(token);
}

/** The header's admin link, or null. Only ever set for an admin. */
export function getAdminLink(): Promise<AdminLink | null> {
  return ensureServerSession().then((info) => info.adminLink ?? null);
}

/**
 * The one place every page's 401 handler should route through
 * (see practice/page.tsx, practice/[id]/page.tsx, admin/page.tsx).
 * clearTokens() is already called by refreshTokens() on failure,
 * but repeating it here is cheap and keeps this function correct
 * standalone. "reason=expired" is read by app/login/page.tsx to
 * show a fixed, friendly message — never the raw backend response
 * text, which for a dead refresh token is a bare "Invalid refresh
 * token"/401 that would mean nothing to someone who did nothing
 * wrong. Query param, not global state: two tabs hitting this at
 * once both just navigate to the same URL, and /login itself never
 * makes an auth:true call, so this can't loop back into itself.
 */
export function redirectToLoginAfterSessionExpiry(router: {
  replace: (href: string) => void;
}): void {
  clearTokens();
  router.replace("/login?reason=expired");
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();

    if (typeof body?.detail === "string") return body.detail;

    // FastAPI validation errors arrive as a list of objects.
    if (Array.isArray(body?.detail) && body.detail.length > 0) {
      const first = body.detail[0];
      if (typeof first?.msg === "string") return first.msg;
    }
  } catch {
    // Fall through to the status-based message.
  }

  if (response.status >= 500) {
    return "The server could not complete that request. Try again shortly.";
  }

  return "That request could not be completed.";
}

async function refreshTokens(): Promise<boolean> {
  const refresh = getRefreshToken();
  if (!refresh) return false;

  let response: Response;

  try {
    response = await fetch(`${BASE}/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      signal: timeoutSignal(DEFAULT_TIMEOUT_MS),
    });
  } catch {
    // Previously unguarded: a network failure or a stalled
    // connection here threw straight out of request()'s own
    // `await refreshTokens()`, past the 401 handling entirely, as
    // a raw, unrelated-looking exception. Treat exactly like a
    // refresh the server actively rejected.
    clearTokens();
    return false;
  }

  if (!response.ok) {
    clearTokens();
    return false;
  }

  await storeTokens((await response.json()) as Tokens);
  return true;
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /**
   * Sent as-is (not JSON-stringified) when present; body is
   * ignored. For the one caller that PUTs a gzip-compressed
   * payload (visual signals) rather than JSON. Safe to retry on
   * 401: callers pass a Blob/Uint8Array, never a stream.
   */
  rawBody?: BodyInit;
  headers?: Record<string, string>;
  auth?: boolean;
  retryOnAuthFailure?: boolean;
  /** Overrides DEFAULT_TIMEOUT_MS. Not used by any caller today —
   * present so a genuinely slow endpoint can opt into a longer
   * window without changing the default every other call gets. */
  timeoutMs?: number;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    rawBody,
    headers: extraHeaders,
    auth = true,
    retryOnAuthFailure = true,
    timeoutMs = DEFAULT_TIMEOUT_MS,
  } = options;

  const headers: Record<string, string> = { ...extraHeaders };

  if (rawBody === undefined && body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (auth) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;

  try {
    response = await fetch(`${BASE}${path}`, {
      method,
      headers,
      body: rawBody !== undefined ? rawBody : body === undefined ? undefined : JSON.stringify(body),
      signal: timeoutSignal(timeoutMs),
    });
  } catch (caught) {
    // Previously fetch()'s own rejection (a stalled connection
    // with no timeout at all, or a real network failure) just
    // propagated as-is — every caller's `instanceof ApiError`
    // check already treats a non-ApiError as "the request never
    // reached the server," so this only adds a message specific
    // enough to tell someone their connection stalled rather than
    // something being wrong with the request itself.
    if (isTimeout(caught)) {
      throw new ApiError(408, "The request timed out. Check your connection and try again.");
    }
    throw caught;
  }

  // An expired access token is the common case, not an error.
  // Swap it for a fresh one and replay once.
  if (response.status === 401 && auth && retryOnAuthFailure) {
    if (await refreshTokens()) {
      return request<T>(path, { ...options, retryOnAuthFailure: false });
    }
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

/* ---------------------------------------------------------- */
/* Auth                                                        */
/* ---------------------------------------------------------- */

export async function signup(input: {
  email: string;
  password: string;
  first_name: string;
  last_name: string;
}): Promise<Tokens> {
  const tokens = await request<Tokens>("/v1/auth/signup", {
    method: "POST",
    body: input,
    auth: false,
  });

  await storeTokens(tokens);
  return tokens;
}

export async function login(input: {
  email: string;
  password: string;
}): Promise<Tokens> {
  const tokens = await request<Tokens>("/v1/auth/login", {
    method: "POST",
    body: input,
    auth: false,
  });

  await storeTokens(tokens);
  return tokens;
}

export function getCurrentUser(): Promise<User> {
  return request<User>("/v1/users/me");
}

/**
 * Permanently deletes the signed-in account: every session, every
 * stored recording/transcript/report, everything. The backend
 * re-checks the password itself (app/routes/users.py) — this
 * function carries it, but it is not what authorizes the delete.
 * Throws ApiError(401, "Incorrect password.") on a wrong password;
 * the caller is expected to keep its confirmation UI open and show
 * that, not just retry or redirect.
 */
export function deleteAccount(password: string): Promise<void> {
  return request<void>("/v1/users/me", {
    method: "DELETE",
    body: { password },
  });
}

/**
 * Fallback for LastSeenMiddleware (app/core/last_seen.py), which
 * only fires on requests that hit some other endpoint. Called on
 * an interval while a signed-in tab is open — see
 * components/Heartbeat.tsx — so a tab idling on a page that
 * makes no other API calls still counts as active. Errors are
 * swallowed by the caller; a missed heartbeat isn't worth
 * surfacing to the user.
 */
export function heartbeat(): Promise<void> {
  // retryOnAuthFailure: false — heartbeat fires on a timer with no
  // real user interaction behind it (Heartbeat.tsx), so letting a
  // dead access token silently refresh here would mean a tab left
  // open and forgotten keeps the session alive forever: the
  // refresh token's idle timeout can never be reached as long as
  // *something* is pinging every 60s. A genuine user action (a
  // real page load, a real API call from something the user is
  // actually doing) still refreshes normally through the default
  // path elsewhere in this file.
  return request<void>("/v1/users/heartbeat", {
    method: "POST",
    retryOnAuthFailure: false,
  });
}

/* ---------------------------------------------------------- */
/* Sessions                                                    */
/* ---------------------------------------------------------- */

export function listSessions(): Promise<SessionSummary[]> {
  return request<SessionSummary[]>("/v1/sessions");
}

export function getSession(id: string): Promise<SessionSummary> {
  return request<SessionSummary>(`/v1/sessions/${id}`);
}

export function getProgress(
  metric: ProgressMetric,
  range: ProgressRange,
): Promise<ProgressPoint[]> {
  const query = new URLSearchParams({ metric, range });
  return request<ProgressPoint[]>(`/v1/sessions/progress?${query}`);
}

export function getReport(id: string): Promise<SessionReport> {
  return request<SessionReport>(`/v1/sessions/${id}/report`);
}

export function deleteSession(id: string): Promise<void> {
  return request<void>(`/v1/sessions/${id}`, { method: "DELETE" });
}

export function createSession(input: {
  content_type: string;
  title: string | null;
  /** Defaults to "not_requested" server-side when omitted. */
  video_analysis?: "requested" | "not_requested";
}): Promise<SessionCreated> {
  return request<SessionCreated>("/v1/sessions", {
    method: "POST",
    body: input,
  });
}

export interface VideoFinalize {
  status: "uploaded" | "unavailable";
  reason?: string;
}

/**
 * video is omitted entirely (not even as {video: undefined}) when
 * not given, so a caller with no video outcome gets exactly the
 * bodyless POST this route has always accepted.
 */
export function startSession(id: string, video?: VideoFinalize): Promise<SessionSummary> {
  return request<SessionSummary>(`/v1/sessions/${id}/start`, {
    method: "POST",
    body: video ? { video } : undefined,
  });
}

/**
 * PUT a built, already-serialized-and-compressed VisualSignalTrack.
 * gzip is preferred (see features/video-analysis/upload.ts); pass
 * null contentEncoding to send plain JSON when CompressionStream
 * isn't available.
 */
export function uploadVisualSignals(
  sessionId: string,
  body: BodyInit,
  contentEncoding: "gzip" | null,
): Promise<{ status: string; frames: number }> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (contentEncoding) headers["Content-Encoding"] = contentEncoding;

  return request(`/v1/sessions/${sessionId}/visual-signals`, {
    method: "PUT",
    rawBody: body,
    headers,
  });
}

/**
 * PUTs straight to a GCS signed URL — never through request(), since
 * the API server never sees these bytes at all (see uploadAndStart's
 * own doc). Shared by uploadAndStart below and by Recorder.tsx's
 * video-analysis path, which needs the same PUT with different
 * steps around it. Previously each had its own inline fetch() with
 * no timeout; a stalled connection left "Sending" on screen with no
 * way to know it had stalled rather than just being slow.
 */
export async function putToSignedUrl(
  url: string,
  headers: Record<string, string>,
  body: BodyInit,
): Promise<void> {
  let response: Response;

  try {
    response = await fetch(url, {
      method: "PUT",
      headers,
      body,
      signal: timeoutSignal(UPLOAD_TIMEOUT_MS),
    });
  } catch (caught) {
    throw new ApiError(
      isTimeout(caught) ? 408 : 0,
      isTimeout(caught)
        ? "The upload timed out. Check your connection and try again."
        : "The recording could not be uploaded. Check your connection and try again.",
    );
  }

  if (!response.ok) {
    throw new ApiError(
      response.status,
      "The recording could not be uploaded. Check your connection and try again.",
    );
  }
}

/**
 * Reserve a session, PUT the audio straight to object storage,
 * then tell the API to begin.
 *
 * The recording never passes through the API server, so upload
 * speed is bounded by the storage provider rather than by our
 * own bandwidth.
 */
export async function uploadAndStart(
  blob: Blob,
  title: string | null,
): Promise<string> {
  const contentType = blob.type.split(";")[0] || "audio/webm";

  const created = await createSession({
    content_type: contentType,
    title,
  });

  await putToSignedUrl(created.upload_url, created.upload_headers, blob);

  await startSession(created.id);

  return created.id;
}

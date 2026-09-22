import type {
  AdminStats,
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

export function storeTokens(tokens: Tokens): void {
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
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

  const response = await fetch(`${BASE}/v1/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refresh }),
  });

  if (!response.ok) {
    clearTokens();
    return false;
  }

  storeTokens((await response.json()) as Tokens);
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
}

async function request<T>(
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
  } = options;

  const headers: Record<string, string> = { ...extraHeaders };

  if (rawBody === undefined && body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  if (auth) {
    const token = getAccessToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: rawBody !== undefined ? rawBody : body === undefined ? undefined : JSON.stringify(body),
  });

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

  storeTokens(tokens);
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

  storeTokens(tokens);
  return tokens;
}

export function getCurrentUser(): Promise<User> {
  return request<User>("/v1/users/me");
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
  return request<void>("/v1/users/heartbeat", { method: "POST" });
}

/* ---------------------------------------------------------- */
/* Admin                                                        */
/* ---------------------------------------------------------- */

export function getAdminStats(): Promise<AdminStats> {
  return request<AdminStats>("/v1/admin/stats");
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

  const upload = await fetch(created.upload_url, {
    method: "PUT",
    headers: created.upload_headers,
    body: blob,
  });

  if (!upload.ok) {
    throw new ApiError(
      upload.status,
      "The recording could not be uploaded. Check your connection and try again.",
    );
  }

  await startSession(created.id);

  return created.id;
}

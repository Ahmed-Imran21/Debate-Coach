/**
 * Share-link helpers, free of React so vitest can test them.
 */

/** The public URL for a share token, on this site's own origin. */
export function shareUrl(origin: string, token: string): string {
  return `${origin.replace(/\/$/, "")}/shared/${encodeURIComponent(token)}`;
}

/**
 * The one message for every way a shared report can be unavailable
 * (wrong, revoked, replaced, deleted): never a hint of which.
 */
export const SHARED_UNAVAILABLE = "This report isn't available.";

// Response headers for the public shared-report page, used by both
// next.config.mjs and middleware.ts so the two can't drift apart.
// Plain .mjs so next.config.mjs can import it without a build step.
export const SHARED_PAGE_HEADERS = [
  { key: "X-Robots-Tag", value: "noindex, nofollow" },
  { key: "Cache-Control", value: "private, no-store" },
  { key: "Referrer-Policy", value: "no-referrer" },
];

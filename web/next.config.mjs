/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,

  async headers() {
    const apiOrigin =
      process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

    // Audio uploads go straight to object storage, so the
    // storage origin has to be allowed for connect-src too.
    const storageOrigin = process.env.NEXT_PUBLIC_STORAGE_ORIGIN ?? "";

    // `next dev` sets NODE_ENV to "development" before loading this
    // file; `next build` and `next start` set "production". Anything
    // unexpected falls through to the strict (production) policy.
    const isDev = process.env.NODE_ENV === "development";

    const csp = [
      "default-src 'self'",
      // 'unsafe-inline' is required: the App Router ships the RSC
      // payload in inline <script> tags (self.__next_f.push(...)),
      // and without a nonce the browser blocks every one of them,
      // leaving the page hydrated with no data — a white screen.
      // Hardening this further means issuing a per-request nonce
      // from middleware, which opts every route into dynamic
      // rendering.
      // 'wasm-unsafe-eval' is separate from 'unsafe-inline' above:
      // it is what lets WebAssembly.instantiate compile the
      // MediaPipe runtime at all under a strict script-src. Only
      // loaded post opt-in (see features/video-analysis), and
      // only from same-origin /mediapipe/wasm — never a CDN.
      // 'unsafe-eval' is added in development only: `next dev` wraps
      // each module in eval() for source maps and Fast Refresh, and
      // without it hydration never runs — forms then fall back to a
      // native GET that puts their fields in the URL. Next's
      // production bundles don't use eval(), so builds stay strict.
      `script-src 'self' 'unsafe-inline' 'wasm-unsafe-eval'${isDev ? " 'unsafe-eval'" : ""}`,
      "style-src 'self' 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src 'self'",
      `connect-src 'self' ${apiOrigin} ${storageOrigin}`.trim(),
      "media-src 'self' blob: https:",
      "frame-ancestors 'none'",
      "base-uri 'self'",
      "form-action 'self'",
    ].join("; ");

    return [
      {
        source: "/:path*",
        headers: [
          { key: "Content-Security-Policy", value: csp },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "DENY" },
          {
            key: "Permissions-Policy",
            // camera=(self): visual analysis is opt-in and only
            // ever requested from this origin (see §0.3.4 rule 4 —
            // no video leaves the browser regardless).
            value: "camera=(self), geolocation=(), microphone=(self)",
          },
          {
            key: "Strict-Transport-Security",
            value: "max-age=63072000; includeSubDomains; preload",
          },
        ],
      },
    ];
  },
};

export default nextConfig;

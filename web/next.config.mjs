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

    const csp = [
      "default-src 'self'",
      // 'unsafe-inline' is required: the App Router ships the RSC
      // payload in inline <script> tags (self.__next_f.push(...)),
      // and without a nonce the browser blocks every one of them,
      // leaving the page hydrated with no data — a white screen.
      // Hardening this further means issuing a per-request nonce
      // from middleware, which opts every route into dynamic
      // rendering.
      "script-src 'self' 'unsafe-inline'",
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
            value: "camera=(), geolocation=(), microphone=(self)",
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

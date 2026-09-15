import type { Metadata, Viewport } from "next";
import { IBM_Plex_Sans, Newsreader } from "next/font/google";

import "./globals.css";

/**
 * Both faces are downloaded at build time and served from our
 * own origin. Nothing is requested from Google at runtime, so
 * no font CDN sees a visitor's IP address. The privacy policy
 * says this, so it needs to stay true.
 */
const serif = Newsreader({
  subsets: ["latin"],
  weight: ["400", "500"],
  style: ["normal", "italic"],
  display: "swap",
  variable: "--font-serif",
});

const sans = IBM_Plex_Sans({
  subsets: ["latin"],
  weight: ["400", "500", "600"],
  display: "swap",
  variable: "--font-sans",
});

const siteUrl =
  process.env.NEXT_PUBLIC_SITE_URL ?? "https://yourdomain.com";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Debate Coach",
    template: "%s — Debate Coach",
  },
  description:
    "Record a practice debate speech and get it back marked up: pace, pauses and filler words counted from the audio, and your argument structure read back to you.",
  applicationName: "Debate Coach",
  openGraph: {
    type: "website",
    siteName: "Debate Coach",
    title: "Debate Coach",
    description:
      "Record a practice debate speech and get it back marked up, second by second.",
    url: siteUrl,
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  themeColor: "#edefea",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${serif.variable} ${sans.variable}`}>
      <body>{children}</body>
    </html>
  );
}

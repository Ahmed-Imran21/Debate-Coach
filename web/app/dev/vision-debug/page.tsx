import type { Metadata } from "next";
import { notFound } from "next/navigation";
import type { ReactElement } from "react";

import VisionDebugClient from "./VisionDebugClient";

export const metadata: Metadata = {
  title: "Vision debug",
  robots: { index: false, follow: false },
};

/**
 * Dev-only (task doc §4.12): a real 404 in production, not just
 * hidden UI, and never linked from production navigation. This is
 * how head-pose signs, iris direction and handedness mapping get
 * verified against a real camera — see
 * docs/video-analysis/MANUAL_TEST_PLAN.md.
 */
export default function VisionDebugPage(): ReactElement {
  if (process.env.NODE_ENV === "production" && process.env.NEXT_PUBLIC_VISION_DEBUG !== "true") {
    notFound();
  }

  return <VisionDebugClient />;
}

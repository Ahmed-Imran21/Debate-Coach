"use client";

import { useEffect } from "react";

import { warmUpBackend } from "@/lib/api";

/**
 * Mounted once, in the root layout: on every page load, a
 * fire-and-forget GET /health wakes a scaled-to-zero backend while the
 * user reads, so the page's first real request rarely waits on a cold
 * start. Renders nothing.
 */
export default function BackendWarmup(): null {
  useEffect(() => {
    warmUpBackend();
  }, []);

  return null;
}

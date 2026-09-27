import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Runs the golden generator with the website's own vitest, against the
// website's own modules (../../web/features/video-analysis). Nothing in
// web/ is modified; see README.md in this folder.
export default defineConfig({
  root: fileURLToPath(new URL(".", import.meta.url)),
  test: {
    environment: "node",
    include: ["generate-goldens.test.ts"],
  },
});

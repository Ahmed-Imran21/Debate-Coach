import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Pure TypeScript modules (video-analysis math, scheduler, track
// builder), plus server-rendered markup of a component where its
// initial state matters (react-dom/server needs no DOM). No DOM, no
// MediaPipe — those need a browser and are covered by the manual
// test plan and the debug page instead. Keep this config minimal.
export default defineConfig({
  // tsconfig's "preserve" is for Next's own compiler; tests render
  // components with the automatic runtime.
  oxc: { jsx: { runtime: "automatic" } },
  // Same "@/..." alias tsconfig.json declares, for modules that use it.
  resolve: {
    alias: { "@": fileURLToPath(new URL(".", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: [
      "features/**/__tests__/**/*.test.ts",
      "lib/**/__tests__/**/*.test.ts",
    ],
  },
});

import { defineConfig } from "vitest/config";

// Pure TypeScript modules only (video-analysis math, scheduler,
// track builder). No DOM, no component rendering, no MediaPipe —
// those need a browser and are covered by the manual test plan
// and the debug page instead. Keep this config minimal.
export default defineConfig({
  test: {
    environment: "node",
    include: [
      "features/**/__tests__/**/*.test.ts",
      "lib/**/__tests__/**/*.test.ts",
    ],
  },
});

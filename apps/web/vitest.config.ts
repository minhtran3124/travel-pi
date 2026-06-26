import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    // Keep the fast unit runner scoped to src/. Playwright e2e specs live in
    // ./playwright (run via `pnpm e2e`) and must NOT be collected by vitest.
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});

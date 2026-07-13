import { fileURLToPath } from "node:url"
import { defineConfig } from "vitest/config"

const src = (path: string) => fileURLToPath(new URL(`./src/${path}`, import.meta.url))

export default defineConfig({
  resolve: {
    alias: {
      "@": src(""),
      // The real package throws outside a React Server Components build.
      "server-only": src("test/empty.ts"),
    },
  },
  test: { environment: "node", include: ["src/**/*.test.ts"] },
})

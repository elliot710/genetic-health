import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

// Scoped to the Effect layer only. This is not a mandate to backfill component
// tests -- it exists so the new async runtime is not shipped unverified.
export default defineConfig({
  test: {
    include: ['src/lib/effect/**/*.test.ts'],
    environment: 'node',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})

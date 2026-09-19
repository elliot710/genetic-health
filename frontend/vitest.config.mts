import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'

// Scoped to the Effect layer plus the component tests that guard how clinical
// findings are worded on screen. Not a mandate to backfill component tests.
// Default environment stays node; component files opt into jsdom with a
// `@vitest-environment jsdom` docblock, which avoids paying for a DOM in the
// Effect suite.
export default defineConfig({
  plugins: [react()],
  test: {
    include: [
      'src/lib/effect/**/*.test.ts',
      'src/components/**/__tests__/**/*.test.tsx',
    ],
    environment: 'node',
  },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
})

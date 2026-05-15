import path from 'node:path'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [
    tailwindcss(),
    react(),
  ],
  resolve: {
    alias: {
      '@/app':      path.resolve(__dirname, 'src/app'),
      '@/pages':    path.resolve(__dirname, 'src/pages'),
      '@/widgets':  path.resolve(__dirname, 'src/widgets'),
      '@/features': path.resolve(__dirname, 'src/features'),
      '@/entities': path.resolve(__dirname, 'src/entities'),
      '@/shared':   path.resolve(__dirname, 'src/shared'),
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test/setup.ts',
    globals: true,
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html', 'lcov'],
      include: ['src/shared/**', 'src/entities/**', 'src/widgets/**'],
      exclude: ['**/*.test.{ts,tsx}', '**/index.ts', 'src/test/**'],
      thresholds: { lines: 80, functions: 80, statements: 80, branches: 75 },
    },
  },
})

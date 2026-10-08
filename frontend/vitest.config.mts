import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.ts'],
    globals: true,
    clearMocks: true,
    unstubGlobals: true,
    unstubEnvs: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      all: true,
      include: ['src/**/*.{ts,tsx}'],
      // Ficam de fora apenas testes, helpers de teste, o layout raiz e um arquivo só de tipos (sem código executável).
      exclude: ['src/**/*.test.{ts,tsx}', 'src/setupTests.ts', 'src/test/**', 'src/app/layout.tsx', 'src/components/politician/types.ts'],
      thresholds: {
        // Valores medidos (linhas/instruções 98, funções 87, branches 90) menos uma pequena margem.
        lines: 95,
        functions: 83,
        branches: 86,
        statements: 95
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
});

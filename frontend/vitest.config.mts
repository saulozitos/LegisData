import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import { resolve } from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    testTimeout: 15000,
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
      exclude: ['src/**/*.test.{ts,tsx}', 'src/setupTests.ts', 'src/test/**', 'src/app/layout.tsx', 'src/components/politician/types.ts', 'src/schemas/**'],
      thresholds: {
        // Valores medidos com o Vitest 5 (linhas 92,4, instruções 91,3, funções 89,9, branches 85,5) menos uma pequena
        // margem. O coverage-v8 5 mapeia a cobertura pela árvore do código e conta como não coberto o que o 2.x
        // dava como coberto (manipuladores `onClick` e o `content` do Tooltip do Recharts, que o jsdom não aciona); com
        // os mesmos testes o v2 media linhas 96,6 e branches 87,2. Subir de novo exige testar esses trechos.
        lines: 92,
        functions: 83,
        branches: 85,
        statements: 91
      }
    }
  },
  resolve: {
    alias: {
      '@': resolve(__dirname, './src'),
    },
  },
});

import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    "coverage/**",
  ]),
  {
    rules: {
      // Regras de hooks são erros: violações quebram a renderização em runtime.
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "error",
      "react-hooks/set-state-in-effect": "error",
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": "error",
      "react/no-unescaped-entities": "error",
      // O app usa <img> simples (fotos externas de domínios oficiais, restritos pela CSP em next.config.ts),
      // sem o otimizador do next/image; a escolha é única e consistente em todo o código.
      "@next/next/no-img-element": "off",
    },
  },
  {
    // Testes usam mocks tipados de forma flexível.
    files: ["**/*.test.{ts,tsx}", "src/setupTests.ts"],
    rules: {
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/no-unused-vars": "warn",
    },
  },
]);

export default eslintConfig;

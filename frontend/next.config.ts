import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

// Origem absoluta da API quando o frontend a consome diretamente (NEXT_PUBLIC_API_URL).
function resolveApiOrigin(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return "";
  try {
    return new URL(raw).origin;
  } catch {
    return "";
  }
}

// Fotos oficiais de parlamentares e presidentes vêm destes domínios (o app usa <img> simples, sem otimizador).
const IMAGE_HOSTS = [
  "https://upload.wikimedia.org",
  "https://*.wikimedia.org",
  "https://*.camara.leg.br",
  "https://*.senado.leg.br",
];

const csp = [
  "default-src 'self'",
  // Next.js injeta scripts inline para hidratação; sem nonces por requisição, 'unsafe-inline' é necessário.
  `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
  "style-src 'self' 'unsafe-inline'",
  `img-src 'self' data: blob: ${IMAGE_HOSTS.join(" ")}`,
  "font-src 'self' data:",
  `connect-src 'self'${resolveApiOrigin() ? ` ${resolveApiOrigin()}` : ""}${isDev ? " ws: http://localhost:*" : ""}`,
  "object-src 'none'",
  "base-uri 'self'",
  "form-action 'self'",
  "frame-ancestors 'none'",
  ...(isDev ? [] : ["upgrade-insecure-requests"]),
].join("; ");

const securityHeaders = [
  { key: "Content-Security-Policy", value: csp },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=()" },
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains; preload" },
  { key: "Cross-Origin-Opener-Policy", value: "same-origin" },
];

const nextConfig: NextConfig = {
  // Imagem Docker enxuta: `next build` gera .next/standalone com apenas as dependências necessárias.
  output: "standalone",
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: securityHeaders,
      },
    ];
  },
  async rewrites() {
    // Avaliado em build; para trocar o backend em runtime use NEXT_PUBLIC_API_URL ou proxy reverso.
    const backendUrl = process.env.INTERNAL_BACKEND_URL || "http://backend:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
      {
        // Verificação de disponibilidade usada pelo selo do cabeçalho.
        source: "/api/health",
        destination: `${backendUrl}/health`,
      },
    ];
  },
};

export default nextConfig;

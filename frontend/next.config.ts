import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV !== "production";

// Origem da API externa (se o frontend consumir a API diretamente em vez do rewrite /api/v1).
function apiOrigin(): string | null {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return null;
  try {
    return new URL(raw).origin;
  } catch {
    return null;
  }
}

// Content-Security-Policy compatível com o Next App Router.
// 'unsafe-inline' em script-src/style-src é necessário por ora (scripts inline de hidratação
// do Next e estilos inline de bibliotecas como Recharts). Evoluir para nonces futuramente.
function contentSecurityPolicy(): string {
  const connectSrc = ["'self'"];
  const origin = apiOrigin();
  if (origin) connectSrc.push(origin);
  if (isDev) connectSrc.push("ws:", "wss:"); // HMR do `next dev`

  const directives = [
    "default-src 'self'",
    // 'unsafe-eval' apenas em desenvolvimento (React Refresh / next dev)
    `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ""}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: https://*.camara.leg.br https://*.senado.leg.br https://*.wikimedia.org",
    "font-src 'self' data:",
    `connect-src ${connectSrc.join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ];
  // Fotos legadas com http:// (ex.: www.senado.leg.br) são promovidas a https em produção.
  if (!isDev) directives.push("upgrade-insecure-requests");
  return directives.join("; ");
}

const securityHeaders = [
  { key: "Content-Security-Policy", value: contentSecurityPolicy() },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
  async rewrites() {
    const backendUrl = process.env.INTERNAL_BACKEND_URL || "http://backend:8000";
    return [
      {
        source: "/api/v1/:path*",
        destination: `${backendUrl}/api/v1/:path*`,
      },
    ];
  },
  images: {
    unoptimized: true,
    remotePatterns: [
      {
        protocol: "https",
        hostname: "upload.wikimedia.org",
      },
      {
        protocol: "https",
        hostname: "**.wikimedia.org",
      },
      {
        protocol: "https",
        hostname: "**.camara.leg.br",
      },
      {
        protocol: "https",
        hostname: "**.senado.leg.br",
      },
    ],
  },
};

export default nextConfig;

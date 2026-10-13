# syntax=docker/dockerfile:1

# ---- Dependências (cacheadas enquanto package*.json não mudar; npm ci respeita o lockfile)
FROM node:26-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# ---- Build
FROM node:26-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ARG NEXT_PUBLIC_API_URL
# Os rewrites do Next.js são resolvidos em build: para outro backend, reconstrua com --build-arg.
ARG INTERNAL_BACKEND_URL=http://backend:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-}
ENV INTERNAL_BACKEND_URL=${INTERNAL_BACKEND_URL}
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# ---- Runtime (saída standalone: sem node_modules completo nem devDependencies)
FROM node:26-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

# Criação de grupo e usuário não-root para execução segura no Alpine
RUN addgroup -g 1001 -S appuser && \
    adduser -u 1001 -S appuser -G appuser

COPY --chown=appuser:appuser --from=builder /app/.next/standalone ./
COPY --chown=appuser:appuser --from=builder /app/.next/static ./.next/static
COPY --chown=appuser:appuser --from=builder /app/public ./public

USER appuser

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1

CMD ["node", "server.js"]

FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

ARG NEXT_PUBLIC_API_URL
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-}
ENV INTERNAL_BACKEND_URL=http://backend:8000
ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV INTERNAL_BACKEND_URL=http://backend:8000
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

COPY --from=builder /app/package*.json ./
COPY --from=builder /app/node_modules ./node_modules
# .next pertence ao usuário "node" para permitir a escrita do cache de runtime do Next
COPY --from=builder --chown=node:node /app/.next ./.next
COPY --from=builder /app/public ./public

# Executa com o usuário sem privilégios já existente na imagem oficial do Node
USER node

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD wget -q --spider http://127.0.0.1:3000/ || exit 1

CMD ["npx", "next", "start", "-p", "3000", "-H", "0.0.0.0"]

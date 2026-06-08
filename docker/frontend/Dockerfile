# Stage 1: build
ARG REGISTRY=""
FROM ${REGISTRY}node:20-alpine AS builder
WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# URL interna del cluster — Next.js proxea /api/v1/* aquí server-side
ENV BACKEND_URL=http://api-gateway.ai-platform.svc.cluster.local

RUN mkdir -p /app/public && npm run build

# Stage 2: runner (imagen mínima con standalone output)
FROM ${REGISTRY}node:20-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV BACKEND_URL=http://api-gateway.ai-platform.svc.cluster.local

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001

COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]

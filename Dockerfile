# syntax=docker/dockerfile:1

FROM oven/bun:1-alpine AS builder
WORKDIR /app

# Install dependencies first for better layer caching.
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile

# Copy source and build Nuxt app.
COPY . .
RUN bun run build

FROM oven/bun:1-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production

# Nuxt standalone output
COPY --from=builder /app/.output ./.output

EXPOSE 3000
CMD ["bun", ".output/server/index.mjs"]

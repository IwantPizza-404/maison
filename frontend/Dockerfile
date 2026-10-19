FROM node:24-alpine AS build
RUN corepack enable && corepack prepare pnpm@10.18.0 --activate
WORKDIR /app
# Сначала только lock-файл: зависимости кэшируются, пока он не меняется
COPY package.json pnpm-lock.yaml ./
RUN pnpm fetch
COPY . .
# Сборке Nuxt не хватает кучи Node по умолчанию (~1 ГБ на сервере с 2 ГБ RAM) — остальное берёт swap
ENV NODE_OPTIONS=--max-old-space-size=3072
RUN pnpm install --offline --frozen-lockfile && pnpm build

FROM node:24-alpine
ENV NODE_ENV=production HOST=0.0.0.0 PORT=3000
WORKDIR /app
COPY --from=build --chown=node:node /app/.output ./.output
USER node
EXPOSE 3000
CMD ["node", ".output/server/index.mjs"]

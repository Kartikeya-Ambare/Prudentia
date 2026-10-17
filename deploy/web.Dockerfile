# Builds the frontend, then serves it with Caddy, which also forwards /api and /chat-api to the two services (one address, no CORS).
FROM node:22-alpine AS build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build

FROM caddy:2-alpine
COPY --from=build /app/frontend/dist /srv
COPY deploy/Caddyfile /etc/caddy/Caddyfile

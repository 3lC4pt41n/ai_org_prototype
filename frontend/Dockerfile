# Stage 1: build React app
FROM node:20 AS build
WORKDIR /app
COPY . /app
RUN npm install -g pnpm && pnpm install
RUN pnpm --filter web build

# Stage 2: serve with nginx
FROM nginx:1.25-alpine AS prod
RUN apk add --no-cache curl
COPY --from=build /app/apps/web/dist /usr/share/nginx/html
COPY ops/nginx.conf /etc/nginx/conf.d/default.conf

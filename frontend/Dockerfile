# --------- Build Stage ---------------------------------------------------------
FROM node:20 AS build
WORKDIR /app

# PNPM aktivieren (Corepack ist ab Node 20 enthalten)
RUN corepack enable && corepack prepare pnpm@9 --activate

# Workspace-/Root-Dateien zuerst (bessere Caching-Schichten)
COPY pnpm-lock.yaml* pnpm-workspace.yaml* package.json ./
# Apps/Packages übernehmen (minimaler Kontext dank frontend/.dockerignore)
COPY apps ./apps
COPY packages ./packages 2>/dev/null || true

# Install (Workspace-weit) – lockfile enforced
RUN pnpm install --frozen-lockfile

# Build nur für das Web-Frontend (falls Filter nicht verfügbar, Fallback auf app-dir)
RUN pnpm --filter ./apps/web build || pnpm --dir apps/web build

# Export-Ordner erkennen und nach /tmp/export kopieren (robuste Fallbacks)
RUN set -eux; \
    if [ -d "apps/web/out" ]; then \
      cp -r apps/web/out /tmp/export; \
    elif [ -d "apps/web/dist" ]; then \
      cp -r apps/web/dist /tmp/export; \
    elif [ -d "apps/web/build" ]; then \
      cp -r apps/web/build /tmp/export; \
    elif [ -d "apps/web/.next" ] && [ -d "apps/web/.next/static" ]; then \
      mkdir -p /tmp/export/_next/static; \
      cp -r apps/web/.next/static /tmp/export/_next/; \
      if [ -f "apps/web/public/index.html" ]; then cp apps/web/public/index.html /tmp/export/index.html || true; fi; \
      if [ -d "apps/web/public" ]; then cp -r apps/web/public/* /tmp/export/ || true; fi; \
    else \
      echo "❌ Kein bekannter Build-Output (out/dist/build/.next) gefunden."; \
      echo "   Bitte stelle sicher, dass 'pnpm --filter ./apps/web build' statische Artefakte erzeugt."; \
      exit 2; \
    fi

# --------- Runtime Stage (nginx) ----------------------------------------------
FROM nginx:1.25-alpine AS prod
WORKDIR /usr/share/nginx/html

# curl für Container-Healthchecks / Debug (optional)
RUN apk add --no-cache curl

# Nginx-Konfiguration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Statisches Build übernehmen
COPY --from=build /tmp/export ./

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]


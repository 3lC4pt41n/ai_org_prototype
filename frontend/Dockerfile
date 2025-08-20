# --------- Build Stage ---------------------------------------------------------
FROM node:20 AS build
WORKDIR /app

# PNPM aktivieren (Corepack ist ab Node 20 enthalten)
RUN corepack enable && corepack prepare pnpm@9 --activate

# 👉 Einmal den (kleinen) Frontend-Kontext kopieren – dank frontend/.dockerignore ohne node_modules etc.
COPY . .

# 👉 Install: wenn Lockfile da, strikt; sonst normal
RUN if [ -f pnpm-lock.yaml ]; then pnpm install --frozen-lockfile; else pnpm install; fi

# 👉 Build: bevorzugt Workspace-App apps/web, sonst Root-Build-Script
RUN set -eux; \
  if [ -d "apps/web" ]; then \
    pnpm --filter ./apps/web build || pnpm --dir apps/web build; \
  else \
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.build?0:1)"; then \
      pnpm build; \
    else \
      echo '❌ Kein Build-Script gefunden (weder apps/web noch root).'; exit 2; \
    fi; \
  fi

# 👉 Export-Ordner finden und nach /tmp/export kopieren (robust für Next/Vite/CRA)
RUN set -eux; \
  mkdir -p /tmp/export; \
  if [ -d "apps/web/out" ]; then \
    cp -r apps/web/out/* /tmp/export/; \
  elif [ -d "apps/web/dist" ]; then \
    cp -r apps/web/dist/* /tmp/export/; \
  elif [ -d "apps/web/build" ]; then \
    cp -r apps/web/build/* /tmp/export/; \
  elif [ -d "apps/web/.next" ] && [ -d "apps/web/.next/static" ]; then \
    mkdir -p /tmp/export/_next/static; \
    cp -r apps/web/.next/static /tmp/export/_next/; \
    if [ -d "apps/web/public" ]; then cp -r apps/web/public/* /tmp/export/ || true; fi; \
    if [ -f "apps/web/public/index.html" ]; then cp apps/web/public/index.html /tmp/export/index.html || true; fi; \
  elif [ -d "out" ]; then \
    cp -r out/* /tmp/export/; \
  elif [ -d "dist" ]; then \
    cp -r dist/* /tmp/export/; \
  elif [ -d "build" ]; then \
    cp -r build/* /tmp/export/; \
  elif [ -d ".next" ] && [ -d ".next/static" ]; then \
    mkdir -p /tmp/export/_next/static; \
    cp -r .next/static /tmp/export/_next/; \
    if [ -d "public" ]; then cp -r public/* /tmp/export/ || true; fi; \
    if [ -f "public/index.html" ]; then cp public/index.html /tmp/export/index.html || true; fi; \
  else \
    echo "❌ Kein bekannter Build-Output (out/dist/build/.next) gefunden."; \
    echo "   Bitte stelle sicher, dass der Build statische Artefakte erzeugt."; \
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


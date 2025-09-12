# --------- Build stage ---------------------------------------------------------
FROM node:20 AS build
ENV PNPM_HOME="/pnpm"
ENV PATH="$PNPM_HOME:$PATH"
RUN corepack enable \
 && corepack prepare pnpm@10.13.1 --activate
ENV HUSKY=0
WORKDIR /app

# 👉 Copy the (small) frontend context – thanks to frontend/.dockerignore without node_modules etc.
COPY . .

# 👉 Install dependencies
RUN pnpm install --ignore-scripts --frozen-lockfile || pnpm install --ignore-scripts --no-frozen-lockfile

# 👉 Build: prefer workspace app apps/web, otherwise root build script
RUN set -eux; \
  if [ -d "apps/web" ]; then \
    pnpm --filter ./apps/web build || pnpm --dir apps/web build; \
  else \
    if node -e "const p=require('./package.json'); process.exit(p.scripts&&p.scripts.build?0:1)"; then \
      pnpm build; \
    else \
      echo '❌ No build script found (neither apps/web nor root).'; exit 2; \
    fi; \
  fi

# 👉 Find export folder and copy to /tmp/export (robust for Next/Vite/CRA)
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
    echo "❌ No known build output (out/dist/build/.next) found."; \
    echo "   Please ensure the build produces static artefacts."; \
    exit 2; \
  fi

# --------- Runtime stage (nginx) ----------------------------------------------
FROM nginx:1.25-alpine AS prod
WORKDIR /usr/share/nginx/html

# curl for container healthchecks / debug (optional)
RUN apk add --no-cache curl

# Nginx configuration
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy static build
COPY --from=build /tmp/export ./

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]

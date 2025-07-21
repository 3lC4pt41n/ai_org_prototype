#!/usr/bin/env bash
set -e

# 1. Neues Git-Repo anlegen (oder bestehendes verwenden)
git init -b main

# 2. Node-Projekt initialisieren
npm init -y

# 3. Dev-Abhängigkeiten installieren
npm i -D \
  typescript ts-node \
  eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin \
  prettier eslint-config-prettier \
  husky lint-staged commitizen cz-conventional-changelog commitlint @commitlint/config-conventional \
  semantic-release @semantic-release/{changelog,commit-analyzer,github,npm,release-notes-generator} \
  jest ts-jest @types/jest \
  sonarqube-scanner \
  playwright \
  axe-core \
  supabase \
  vercel \
  expo eas-cli

# 4. Husky & Commitizen initialisieren
npx husky install
npm pkg set scripts.prepare="husky install"
npx commitizen init cz-conventional-changelog --save-dev --save-exact

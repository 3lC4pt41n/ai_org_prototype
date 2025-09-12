#!/usr/bin/env bash
set -e

# 1. Create new Git repo (or use existing one)
git init -b main

# 2. Initialize Node project
npm init -y

# 3. Install dev dependencies
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

# 4. Initialize Husky & Commitizen
npx husky install
npm pkg set scripts.prepare="husky install"
npx commitizen init cz-conventional-changelog --save-dev --save-exact

// project/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
      "@ui": path.resolve(__dirname, "../../packages/ui/src"),
      "@api": path.resolve(__dirname, "../../packages/api-client/src"),
      "@web": path.resolve(__dirname, "src"),
    },
  },
  server: {
    port: 5732,          // fester Port für Dev-Server
    strictPort: true,    // bricht ab, wenn Port belegt
    proxy: {
      "/api": {
        target: process.env.VITE_API_PROXY_TARGET || "http://localhost:8000", // FastAPI Backend
        changeOrigin: true,
      },
    },
  },
  build: {
    sourcemap: true,        // 🔍 Source Maps aktivieren → Debugging in DevTools
    target: "esnext",       // modernere Syntax, bessere Tree-Shaking
    outDir: "dist",         // Standard-Ausgabeordner
    emptyOutDir: true,      // vorher dist leeren
  },
  esbuild: {
    jsx: "automatic",       // React 17+ JSX Transform
    logOverride: {          // weniger Spam in der Konsole
      "this-is-undefined-in-esm": "silent",
    },
  },
});

// project/vite.config.js
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";          // <- GANZES Modul holen

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@ui": path.resolve(__dirname, "../../packages/ui/src"),
      "@api": path.resolve(__dirname, "../../packages/api-client/src"),
      "@web": path.resolve(__dirname, "src"),
      
    }
  },
  server: {
    proxy: {
      // FastAPI läuft auf :8000
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true
      }
    }
  }
});



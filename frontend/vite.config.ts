import path from "path"
import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    // The SPA and API share one origin, as in production: /api goes to
    // uvicorn. The Host header is kept, so the API sees the public origin.
    // The browser tests point it at their own API (playwright.config.ts).
    proxy: {
      "/api": process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000",
    },
  },
})

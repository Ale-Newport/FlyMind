/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const API = process.env.FLYMIND_API ?? "http://127.0.0.1:8000";

export default defineConfig(({ mode }) => ({
  // GitHub Pages serves the project under /<repo>/; local builds use /.
  base: mode === "pages" ? "/FlyMind/" : "/",
  plugins: [react(), tailwindcss()],
  define: {
    __STATIC_DEMO__: JSON.stringify(mode === "pages"),
  },
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      "/api": { target: API, changeOrigin: false },
      "/ws": { target: API.replace("http", "ws"), ws: true },
    },
  },
  build: {
    chunkSizeWarningLimit: 6000,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (id.includes("plotly.js")) return "plotly";
          if (id.includes("/three/") || id.includes("@react-three")) return "three";
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/unit/**/*.test.{ts,tsx}"],
    setupFiles: ["tests/unit/setup.ts"],
  },
}));

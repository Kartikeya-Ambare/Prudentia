import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { existsSync } from "node:fs";
import { resolve } from "node:path";

// Pages live at /intake, /sectors, /chat. Every backend call goes under /api/ and is forwarded to
// FastAPI with that prefix removed, so page URLs never collide with backend endpoints (the
// backend has its own /chat) and the backend itself needs no change and no CORS setup.
export default defineConfig(({ mode, command }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const target = env.VITE_API_URL || "http://127.0.0.1:8000";
  const chatTarget = env.VITE_CHAT_URL || "http://127.0.0.1:8001";
  // Prudie is developed in the sibling `mascot` folder. In dev the app loads it from there directly, so every change to the
  // mascot shows up live (hot reload). Builds use the copy in src/prudie (npm run sync:prudie) so they never
  // depend on a folder outside this one.
  const prudieDir = resolve(env.PRUDIE_SRC || "../mascot", "src", "prudie");
  const livePrudie = command === "serve" && existsSync(prudieDir);
  // Same routing for the dev server and for `npm run preview` (the production build), so a production build can be
  // tried against the real backend and measured with DevTools.
  const proxy = {
    // Chat service (chat-service, port 8001): /chat-api/chat -> /api/chat. Must come before "/api".
    "/chat-api": { target: chatTarget, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/chat-api/, "/api") },
    "/api": { target, changeOrigin: true, rewrite: (path: string) => path.replace(/^\/api/, "") },
  };
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      tsconfigPaths: true,
      alias: (livePrudie ? { "@/prudie": prudieDir } : {}) as Record<string, string>,
      // The mascot folder has no node_modules of its own: resolve React from this project.
      dedupe: ["react", "react-dom"],
    },
    preview: { port: 4173, proxy },
    server: {
      fs: { allow: [process.cwd(), ...(livePrudie ? [prudieDir] : [])] },
      port: 5173,
      proxy,
    },
  };
});

import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all env regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react()],
    resolve: {
      alias: {
        "@": fileURLToPath(new URL("./src", import.meta.url)),
      },
    },
    server: {
      port: 3000,
      proxy: {
        "/api": {
          target: env.API_URL || "http://localhost:8000",
          changeOrigin: true,
          secure: false,
          ws: true,
        },
        "/ws": {
          target: process.env.VITE_WS_PROXY_TARGET ?? "http://localhost:8000",
          ws: true,
          changeOrigin: true,
        },
      },
    },
  };
});

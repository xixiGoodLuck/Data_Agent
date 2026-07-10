import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const apiTarget = loadEnv(mode, ".", "").VITE_API_TARGET || "http://localhost:8002";
  return {
    plugins: [react()],
    server: {
      port: 5175,
      proxy: {
        "/api": apiTarget,
        "/health": apiTarget,
      },
    },
    test: {
      environment: "jsdom",
      setupFiles: "./src/test-setup.ts",
      css: true,
    },
  };
});

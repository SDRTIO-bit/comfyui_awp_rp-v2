import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  base: "/awp/",
  build: {
    outDir: "../frontend/dist",
    emptyOutDir: true,
  },
  server: {
    proxy: {
      "/awp/api": {
        target: "http://localhost:8188",
        changeOrigin: true,
      },
    },
  },
});

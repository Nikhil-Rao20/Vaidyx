import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The build lands in static/tb-nik (served by FastAPI at /static/tb-nik, shell at /tb-nik).
// In development, Vite proxies the API to the running Vaidyx app on :7000.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  base: "/static/tb-nik/",
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  build: {
    outDir: path.resolve(__dirname, "../../static/tb-nik"),
    emptyOutDir: true,
    sourcemap: false,
    chunkSizeWarningLimit: 900,
  },
  server: {
    port: 5173,
    strictPort: true,
    host: "127.0.0.1",
    proxy: {
      "/api": { target: "http://127.0.0.1:7000", changeOrigin: false, ws: true },
      "/static/tb/fonts": { target: "http://127.0.0.1:7000", changeOrigin: false },
    },
  },
});

import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The build lands in static/tb-nik (served by FastAPI at /static/tb-nik, shell at /tb-nik).
// In development, Vite proxies the API to the running Vaidyx app on :7000.
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    {
      // development only: open the website at /tb-nik/... (as on :7000) with live reload; the build is unchanged
      name: "tb-nik-dev-shell",
      apply: "serve",
      configureServer(server) {
        server.middlewares.use((req, _res, next) => {
          const u = req.url || "";
          if ((u === "/tb-nik" || u.startsWith("/tb-nik/") || u.startsWith("/tb-nik?")) && !/\.[a-z0-9]+(\?|$)/i.test(u.split("?")[0])) {
            req.url = "/static/tb-nik/index.html";
          }
          next();
        });
      },
    },
  ],
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

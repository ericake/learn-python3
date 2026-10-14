import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Cartoon Word Pal",
        short_name: "Word Pal",
        display: "standalone",
        orientation: "landscape",
        background_color: "#FFF8EC",
        theme_color: "#F7A1C4",
        icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" }],
      },
      workbox: {
        navigateFallbackDenylist: [/^\/api\//, /^\/media\//],
        runtimeCaching: [
          // 课程素材：内容哈希命名，可长期缓存
          { urlPattern: /\/media\//, handler: "CacheFirst",
            options: { cacheName: "media", expiration: { maxAgeSeconds: 60 * 60 * 24 * 14, maxEntries: 2000 } } },
          // 课程包与首页：联网优先，离线时用缓存
          { urlPattern: /\/api\/v1\/(lessons|home)/, handler: "NetworkFirst",
            options: { cacheName: "lessons", networkTimeoutSeconds: 4, expiration: { maxAgeSeconds: 60 * 60 * 24 * 7 } } },
        ],
      },
    }),
  ],
  server: {
    proxy: { "/api": "http://localhost:8000", "/media": "http://localhost:8000" },
  },
});

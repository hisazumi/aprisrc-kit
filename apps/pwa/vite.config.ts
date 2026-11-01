import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";
import { VitePWA } from "vite-plugin-pwa";

const repositoryRoot = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const localServerTarget = process.env.APRIS_SERVER_URL ?? "http://localhost:8000";
const localWebSocketTarget = localServerTarget.replace(/^http/, "ws");

function localHttps() {
  if (process.env.APRIS_DISABLE_HTTPS === "1") return undefined;

  const certificatePath = process.env.APRIS_TLS_CERT
    ?? resolve(repositoryRoot, ".certs/localhost.pem");
  const keyPath = process.env.APRIS_TLS_KEY
    ?? resolve(repositoryRoot, ".certs/localhost-key.pem");
  const certificateExists = existsSync(certificatePath);
  const keyExists = existsSync(keyPath);

  if (!certificateExists && !keyExists) return undefined;
  if (!certificateExists || !keyExists) {
    throw new Error("Both APRIS_TLS_CERT and APRIS_TLS_KEY must exist to enable local HTTPS.");
  }

  return {
    cert: readFileSync(certificatePath),
    key: readFileSync(keyPath)
  };
}

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["rover.svg"],
      manifest: {
        name: "APRIS Rover Console",
        short_name: "Rover",
        description: "Control and prototype services for the APRIS rover platform",
        theme_color: "#15251f",
        background_color: "#f1f4ec",
        display: "standalone",
        id: "/app",
        start_url: "/service?service=my-service",
        scope: "/",
        shortcuts: [
          {
            name: "Operator Console",
            short_name: "Console",
            url: "/console"
          },
          {
            name: "Playground",
            short_name: "Playground",
            url: "/playground?service=my-service"
          }
        ],
        icons: [
          {
            src: "/rover.svg",
            sizes: "any",
            type: "image/svg+xml",
            purpose: "any maskable"
          }
        ]
      }
    })
  ],
  server: {
    https: localHttps(),
    proxy: {
      "/api": localServerTarget,
      "/ws": {
        target: localWebSocketTarget,
        ws: true
      }
    }
  },
  test: {
    environment: "jsdom",
    maxWorkers: 2
  }
});

import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import securityHeaders from "./securityHeaders";
import apiPreconnect from "./apiPreconnect";

/** Vite config: React, Tailwind, and the `_headers` and preconnect plugins fed the API base. */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");

  return {
    plugins: [
      react(),
      tailwindcss(),
      securityHeaders(env.VITE_API_BASE_URL),
      apiPreconnect(env.VITE_API_BASE_URL),
    ],
    build: {
      // One stylesheet, as before, even though the routes are now split.
      //
      // Vite's default is a stylesheet per async chunk, appended as the chunk
      // loads -- which makes the cascade order depend on the order pages were
      // visited. This app cannot take that: `main.tsx` deliberately loads
      // calendar.css eagerly because `.calRow`, `.calField`, `.calInput` and
      // `.calButton` are the shared form primitives the grades, budget and task
      // dialogs all use, and the base `.container button` rule has already
      // caught five controls that had to override it.
      //
      // The whole stylesheet is 16.5 KB gzipped against the JavaScript's 136 KB.
      // The JavaScript is the entire prize here, so there is nothing to win by
      // splitting this as well and a silent, visual class of bug to lose.
      cssCodeSplit: false,
    },
  };
});

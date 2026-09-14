import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import securityHeaders from "./securityHeaders";

// The project imports Tailwind in globals.css but had no config, so the plugin
// never ran: Preflight shipped while every utility class was silently inert.
// The React plugin is what gives Fast Refresh: without it every save was a full
// page reload that threw away component state. Pinned to v5 because v6 requires
// Vite 8 and this project is on 7.
//
// Now a function rather than a plain object, because the third plugin needs to
// read VITE_API_BASE_URL. `loadEnv` is the same resolution Vite uses for
// `import.meta.env`, so the CSP it writes and the URL the bundle calls come from
// one source -- see securityHeaders.ts.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");

  return {
    plugins: [react(), tailwindcss(), securityHeaders(env.VITE_API_BASE_URL)],
  };
});

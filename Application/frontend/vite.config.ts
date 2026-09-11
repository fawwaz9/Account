import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// The project imports Tailwind in globals.css but had no config, so the plugin
// never ran: Preflight shipped while every utility class was silently inert.
// The React plugin is what gives Fast Refresh: without it every save was a full
// page reload that threw away component state. Pinned to v5 because v6 requires
// Vite 8 and this project is on 7.
export default defineConfig({
  plugins: [react(), tailwindcss()],
});

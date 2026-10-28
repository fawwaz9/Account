import type { HtmlTagDescriptor, Plugin } from "vite";
import { DEFAULT_API_BASE_URL } from "./src/services/apiBase";
import { originOf } from "./securityHeaders";

/**
 * Head-first preconnect link to the API origin, `crossorigin` so CORS calls reuse it.
 * Null for a same-origin or malformed base.
 */
export function preconnectTag(apiBaseUrl: string): HtmlTagDescriptor | null {
  const origin = originOf(apiBaseUrl);
  if (!origin) return null;

  return {
    tag: "link",
    attrs: { rel: "preconnect", href: origin, crossorigin: "" },
    // Before the module script, so the handshake starts alongside the download
    // rather than behind it -- which is the entire point.
    injectTo: "head-prepend",
  };
}

/** Build-only plugin adding the API preconnect hint to index.html. */
export default function apiPreconnect(apiBaseUrl?: string): Plugin {
  const base = (apiBaseUrl ?? DEFAULT_API_BASE_URL).trim();

  return {
    name: "account-api-preconnect",
    // Build only. In development the API is on localhost, where a handshake
    // costs nothing worth a hint.
    apply: "build",
    transformIndexHtml() {
      const tag = preconnectTag(base);
      return tag === null ? [] : [tag];
    },
  };
}

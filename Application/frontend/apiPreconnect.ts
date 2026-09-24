import type { HtmlTagDescriptor, Plugin } from "vite";
import { DEFAULT_API_BASE_URL } from "./src/services/apiBase";
import { originOf } from "./securityHeaders";

/**
 * Starts the connection to the API while the bundle is still downloading.
 *
 * The API is on a different origin to the site, so the first call has to do DNS,
 * TCP and TLS before it can send a byte -- and none of that begins until the
 * bundle has downloaded, parsed, and React has mounted far enough to fetch
 * something. Three round trips, strictly after everything else, on exactly the
 * connection where they cost most. A `preconnect` hint moves them into the gap
 * that was being spent downloading the bundle anyway.
 *
 * **`crossorigin` is required, not decoration.** Every call carries an
 * `Authorization` header, which makes it a CORS request, and an anonymous
 * connection cannot be reused for a credentialled one. Without the attribute
 * the browser warms a connection nothing will ever use and opens a second one
 * when the call comes -- the hint then costs a socket and saves nothing, while
 * looking perfectly correct in the markup.
 *
 * **`originOf` is imported rather than re-derived.** It already distinguishes an
 * absolute URL from a root-relative base from a mistake, and it carries the
 * reason that matters: `new URL("localhost:8001/api")` succeeds, reading
 * "localhost:" as the scheme, and serialises its origin to the *string* "null".
 * A second implementation here would be a second place for that to be got
 * wrong, and this one would be got wrong silently -- a bad hint is ignored by
 * the browser without a word.
 *
 * Nothing is emitted for a same-origin API or a malformed one. The first needs
 * no hint; the second is already reported loudly by `securityHeaders`, which
 * fails the same way for the same input, so saying it twice would only make the
 * real message harder to find.
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

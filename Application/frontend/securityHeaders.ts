import type { Plugin } from "vite";
import { DEFAULT_API_BASE_URL } from "./src/services/apiBase";

/**
 * Emits the `_headers` file Cloudflare Pages reads when it serves the bundle.
 *
 * **Why generated rather than checked in.** Every directive here is fixed
 * except one: `connect-src` has to name the API's origin, and that origin is
 * different for local development, for a preview deploy and for production. A
 * static file could only be right for one of them, and the failure mode for the
 * other two is the worst kind -- the browser refuses the request before it
 * leaves, so the API's logs show nothing at all and the app simply looks down.
 * Deriving it from the same variable the bundle is built with means the two can
 * never drift apart.
 *
 * **Why a `_headers` file at all.** Response headers cannot be set from inside a
 * static bundle. The nginx container that used to serve this is not part of the
 * deployed architecture any more, so the host has to apply them, and `_headers`
 * is how Pages is told. It follows that this file does nothing in the local
 * docker stack, which still serves through nginx -- these headers are verified
 * on the deployed site, not in compose.
 */

const GOOGLE_SIGN_IN = "https://accounts.google.com/gsi/";
const GOOGLE_SIGN_IN_SCRIPT = "https://accounts.google.com/gsi/client";
const GOOGLE_SIGN_IN_STYLE = "https://accounts.google.com/gsi/style";

/**
 * What `connect-src` has to name for this API base to be reachable.
 *
 * An absolute URL contributes its origin. A root-relative base (`/api`) is
 * already same-origin and needs nothing beyond `'self'`, which is a real
 * configuration -- it is what putting the API behind the same hostname looks
 * like. Anything else is a mistake, and returns null so the caller can say so.
 */
export function originOf(apiBaseUrl: string): string | null {
  if (apiBaseUrl.startsWith("/")) return "";
  try {
    const url = new URL(apiBaseUrl);
    // Only http(s) has an origin `connect-src` can name. This is not
    // defensive tidying: `new URL("localhost:8001/api")` *succeeds* -- with no
    // scheme, "localhost:" is read as one -- and its origin serialises to the
    // string "null", which sails straight past the `=== null` check below and
    // puts a bare `null` token into the policy. That matches no origin, so
    // every API call is refused before it is sent, and the warning meant to be
    // loud about exactly this never fires. Omitting the scheme is the likeliest
    // way to set this variable wrongly, and the Pages dashboard is where nobody
    // would see it.
    if (url.protocol !== "http:" && url.protocol !== "https:") return null;
    return url.origin;
  } catch {
    return null;
  }
}

/** `apiOrigin` is an origin to allow, or "" for an API that is already same-origin. */
export function buildCsp(apiOrigin: string): string {
  const directives = [
    // Everything not named below is same-origin only.
    "default-src 'self'",
    // The two that close off injected markup rewriting where the page submits
    // or resolves relative URLs to.
    "base-uri 'self'",
    "form-action 'self'",
    // No plugins, and nobody may frame this app. `frame-ancestors` is the
    // modern half of the X-Frame-Options header set alongside it; both are sent
    // because the old header is what a few older browsers still honour.
    "object-src 'none'",
    "frame-ancestors 'none'",
    // The directive that matters most, and the one kept strict: no inline
    // script, no eval, and exactly one third-party script.
    `script-src 'self' ${GOOGLE_SIGN_IN_SCRIPT}`,
    // 'unsafe-inline' here is a deliberate, narrow concession. Roughly thirty
    // components set a `style={{...}}` attribute -- progress bars whose width
    // is a computed percentage, mostly -- and CSP counts a style *attribute* as
    // inline style. `style-src-attr` would let the rest stay strict but is not
    // supported everywhere, and where it is unsupported those bars silently
    // break. Inline style is a far smaller hole than inline script: it cannot
    // execute anything, and script-src above is what actually stops XSS.
    `style-src 'self' 'unsafe-inline' ${GOOGLE_SIGN_IN_STYLE}`,
    // data: for the icons inlined by the bundler; googleusercontent for the
    // profile picture Google returns with a signed-in account.
    "img-src 'self' data: https://*.googleusercontent.com",
    "font-src 'self' data:",
    ["connect-src 'self'", apiOrigin, GOOGLE_SIGN_IN].filter(Boolean).join(" "),
    // Google Sign-In renders its button and its prompt in iframes.
    `frame-src ${GOOGLE_SIGN_IN}`,
  ];

  // Only when the API is already on https. Adding it to a build that talks to
  // http://localhost would rewrite those calls to https and break every one of
  // them -- the directive applies to the whole document, not just to remote
  // hosts.
  if (apiOrigin.startsWith("https://")) {
    directives.push("upgrade-insecure-requests");
  }

  return directives.join("; ");
}

export function buildHeaders(apiBaseUrl: string): string {
  const apiOrigin = originOf(apiBaseUrl);
  const lines = [
    // A year, and every subdomain. Deliberately *without* `preload`: submitting
    // to the preload list is close to irreversible and is a commitment about
    // every future subdomain, which is not a promise to make for a first deploy.
    "Strict-Transport-Security: max-age=31536000; includeSubDomains",
    // Stops a response being executed as a type it was not served as.
    "X-Content-Type-Options: nosniff",
    // The referrer is sent in full to this origin and as the bare origin
    // elsewhere, so an outbound link never leaks which course or account was
    // being looked at.
    "Referrer-Policy: strict-origin-when-cross-origin",
    "X-Frame-Options: DENY",
    // Nothing in this app uses any of these, so nothing injected into it can.
    "Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()",
    `Content-Security-Policy: ${buildCsp(apiOrigin ?? "")}`,
  ];

  // The comment deliberately avoids writing any directive name. A file like
  // this gets grepped, and a comment containing "connect-src" matches before
  // the real directive does -- which turns a check of the policy into a check
  // of the note about the policy, and it passes either way.
  return `# Generated at build time by securityHeaders.ts -- do not edit by hand.
# The API origin below comes from VITE_API_BASE_URL, which was:
#   ${apiBaseUrl}
/*
${lines.map((line) => `  ${line}`).join("\n")}
`;
}

export default function securityHeaders(apiBaseUrl?: string): Plugin {
  const base = (apiBaseUrl ?? DEFAULT_API_BASE_URL).trim();

  return {
    name: "account-security-headers",
    apply: "build",
    generateBundle() {
      if (originOf(base) === null) {
        // Loud, because the quiet version of this is an app that cannot reach
        // its own API and gives no clue why: the browser refuses the request
        // before it is sent, so the API's own logs stay empty.
        this.warn(
          `VITE_API_BASE_URL is neither an absolute URL nor a path (${JSON.stringify(base)}), ` +
            "so connect-src can only allow 'self' and every API call will be " +
            "blocked by the browser. Set it to the full API address, e.g. " +
            "https://account-api-xxxx.a.run.app/api",
        );
      }
      this.emitFile({ type: "asset", fileName: "_headers", source: buildHeaders(base) });
    },
  };
}

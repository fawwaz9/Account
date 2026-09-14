/**
 * Where the API lives, in one place.
 *
 * Two things have to agree about this and they run at different times: the
 * bundle, which calls the API, and the `_headers` file generated at build time,
 * whose `connect-src` decides whether the browser will *allow* that call. When
 * they disagree the failure is silent from the server's side -- the API never
 * sees the request, so its logs stay clean while every page shows an error.
 * That is the same shape as the CORS bug found in Phase 0, and the fix is the
 * same: one value, read by both.
 */

/** Used when `VITE_API_BASE_URL` is unset, i.e. `npm run dev` against a local backend. */
export const DEFAULT_API_BASE_URL = "http://localhost:8000/api";

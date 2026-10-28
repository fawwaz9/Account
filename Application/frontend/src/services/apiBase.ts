/** API base URL, shared by the bundle and the build-time `_headers` connect-src so they agree. */

/** Fallback base when `VITE_API_BASE_URL` is unset: the local dev backend. */
export const DEFAULT_API_BASE_URL = "http://localhost:8000/api";

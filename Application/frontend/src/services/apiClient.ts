import { ValidationError } from "../features/grades/types"; // adjust path to wherever these live
import { DEFAULT_API_BASE_URL } from "./apiBase";
import { cachedGet, clearApiCache } from "./apiCache";

/** Drop every trailing slash from a URL. */
function stripTrailingSlashes(value: string) {
  let end = value.length;
  while (end > 0 && value[end - 1] === "/") {
    end--;
  }
  return value.slice(0, end);
}

/** API base from `VITE_API_BASE_URL` or the local default, without trailing slashes. */
const API_BASE_URL = stripTrailingSlashes(
  (import.meta.env.VITE_API_BASE_URL ?? DEFAULT_API_BASE_URL).trim()
);

/** Fetch options plus a JSON body and the GET-cache opt-out. */
interface RequestOptions extends RequestInit {
  /** Request body, sent as JSON; null or undefined sends none. */
  data?: unknown;
  /** Leave the GET cache alone: for catch-up writes that clear it only when they wrote. */
  keepCache?: boolean;
}

/** Join a path onto the API base. */
function buildUrl(path: string) {
  const cleanPath = path.replace(/^\/+/, "");
  return cleanPath ? `${API_BASE_URL}/${cleanPath}` : API_BASE_URL;
}

/** True when an error detail is FastAPI's list of validation errors. */
function isValidationErrorArray(detail: unknown): detail is ValidationError[] {
  return (
    Array.isArray(detail) &&
    detail.every((e) => typeof e === "object" && e !== null && "msg" in e && "loc" in e)
  );
}

/** One validation error as `field: message`, minus Pydantic's "Value error, " prefix. */
function formatValidationError(err: ValidationError): string {
  const message = err.msg.replace(/^Value error,\s*/, "");
  const field = err.loc.slice(1).join(".");
  return field ? `${field}: ${message}` : message;
}

/** Readable message from an error body's `detail` or `message`, else the fallback. */
function extractErrorMessage(json: unknown, fallback: string): string {
  const detail = (json as { detail?: unknown; message?: unknown })?.detail
    ?? (json as { message?: unknown })?.message;

  if (typeof detail === "string") {
    return detail;
  }

  if (isValidationErrorArray(detail)) {
    return detail.map(formatValidationError).join(", ");
  }

  if (typeof detail === "object" && detail !== null) {
    return JSON.stringify(detail);
  }

  return fallback;
}

/** Bearer header from the session token; empty when signed out. */
function getAuthHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Send a request; a write without `keepCache` empties the GET cache before and after. */
async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  // A write empties the GET cache, before it goes and after it lands, so no
  // read from before it is shown or stored once it's done (apiCache.ts).
  const writes = options.method !== undefined && options.method !== "GET" && !options.keepCache;
  if (writes) clearApiCache();
  try {
    return await send<T>(path, options);
  } finally {
    if (writes) clearApiCache();
  }
}

/** Fetch and parse the JSON answer; any 401 drops the token and reloads /login. */
async function send<T>(path: string, options: RequestOptions): Promise<T> {
  const { data, headers, keepCache: _keepCache, ...init } = options;
  const body = (data == null) ? undefined : JSON.stringify(data);
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...getAuthHeaders(),
      ...headers,
    },
    body,
  });

  if (response.status === 401) {
    sessionStorage.removeItem("access_token");
    clearApiCache();
    window.location.href = "/login";
    throw new Error("Session expired");
  }

  const text = await response.text();
  const json = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = extractErrorMessage(
      json,
      response.statusText || `Request failed with status ${response.status}`
    );
    throw new Error(message);
  }

  return json as T;
}

/** GET through the cache; `fresh` waits for this request's own answer, for polls. */
export function get<T>(path: string, { fresh = false }: { fresh?: boolean } = {}) {
  return cachedGet<T>(path, sessionStorage.getItem("access_token"),
    () => request<T>(path, { method: "GET" }), fresh);
}

/** POST a JSON body; `keepCache` spares the GET cache. */
export function post<T>(path: string, data: unknown, { keepCache = false }: { keepCache?: boolean } = {}) {
  return request<T>(path, { method: "POST", data, keepCache });
}

/** PATCH a JSON body; empties the GET cache. */
export function patch<T>(path: string, data: unknown) {
  return request<T>(path, { method: "PATCH", data });
}

/** PUT a JSON body; empties the GET cache. */
export function put<T>(path: string, data: unknown) {
  return request<T>(path, { method: "PUT", data });
}

/** DELETE a resource; empties the GET cache. */
export function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}

/** Fetch a file as a Blob with the bearer token, which a plain link cannot send. */
export async function getBlob(path: string): Promise<Blob> {
  const response = await fetch(buildUrl(path), { method: "GET", headers: getAuthHeaders() });
  if (response.status === 401) {
    sessionStorage.removeItem("access_token");
    window.location.href = "/login";
    throw new Error("Session expired");
  }
  if (!response.ok) {
    const text = await response.text();
    let json: unknown = null;
    try { json = text ? JSON.parse(text) : null; } catch { json = null; }
    throw new Error(extractErrorMessage(json, `Request failed with status ${response.status}`));
  }
  return response.blob();
}


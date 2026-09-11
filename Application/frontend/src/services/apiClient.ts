import { ValidationError } from "../features/grades/types"; // adjust path to wherever these live

function stripTrailingSlashes(value: string) {
  let end = value.length;
  while (end > 0 && value[end - 1] === "/") {
    end--;
  }
  return value.slice(0, end);
}

const API_BASE_URL = stripTrailingSlashes(
  (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api").trim()
);

interface RequestOptions extends RequestInit {
  data?: unknown;
}

function buildUrl(path: string) {
  const cleanPath = path.replace(/^\/+/, "");
  return cleanPath ? `${API_BASE_URL}/${cleanPath}` : API_BASE_URL;
}

function isValidationErrorArray(detail: unknown): detail is ValidationError[] {
  return (
    Array.isArray(detail) &&
    detail.every((e) => typeof e === "object" && e !== null && "msg" in e && "loc" in e)
  );
}

/**
 * Pydantic prefixes any message from a `ValueError` in a validator with
 * "Value error, ", so a carefully worded rule reached the user as
 * "Value error, A transfer needs somewhere to go". The prefix names an
 * implementation detail of the server's validation library and tells the reader
 * nothing, so it is dropped.
 */
function formatValidationError(err: ValidationError): string {
  const message = err.msg.replace(/^Value error,\s*/, "");
  const field = err.loc.slice(1).join(".");
  return field ? `${field}: ${message}` : message;
}

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

function getAuthHeaders(): HeadersInit {
  const token = sessionStorage.getItem("access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { data, headers, ...init } = options;
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

export function get<T>(path: string) {
  return request<T>(path, { method: "GET" });
}

export function post<T>(path: string, data: unknown) {
  return request<T>(path, { method: "POST", data });
}

export function patch<T>(path: string, data: unknown) {
  return request<T>(path, { method: "PATCH", data });
}

export function put<T>(path: string, data: unknown) {
  return request<T>(path, { method: "PUT", data });
}

export function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}
import { ValidationError } from "../features/grades/types"; // adjust path to wherever these live

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api/users").replace(/\/+$|\s+$/, "");

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

function formatValidationError(err: ValidationError): string {
  const field = err.loc.slice(1).join(".");
  return field ? `${field}: ${err.msg}` : err.msg;
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

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { data, headers, ...init } = options;
  const body = (data == null) ? undefined : JSON.stringify(data);
  const response = await fetch(buildUrl(path), {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...headers,
    },
    body,
  });

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

export function del<T>(path: string) {
  return request<T>(path, { method: "DELETE" });
}
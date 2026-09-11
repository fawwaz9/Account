import { post } from "./apiClient";

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function loginWithGoogle(idToken: string) {
  return post<TokenResponse>("auth/google", { id_token: idToken });
}

export function loginWithEmail(email: string, password: string) {
  return post<TokenResponse>("auth/login", { email, password });
}

export function registerWithEmail(name: string, email: string, password: string) {
  return post<TokenResponse>("auth/register", { name, email, password });
}

/**
 * Add a first password, or change an existing one, for the signed-in user.
 * `currentPassword` is required only when the account already has one.
 *
 * Returns a **replacement token**, because succeeding here invalidates every
 * session the account had -- including this one. The caller must hand the new
 * token to AuthContext, or its very next request is a 401.
 */
export function setPassword(newPassword: string, currentPassword?: string) {
  return post<TokenResponse>("auth/password", {
    new_password: newPassword,
    current_password: currentPassword ?? null,
  });
}

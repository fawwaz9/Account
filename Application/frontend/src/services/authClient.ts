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
 * Returns 204, so there is no body.
 */
export function setPassword(newPassword: string, currentPassword?: string) {
  return post<null>("auth/password", {
    new_password: newPassword,
    current_password: currentPassword ?? null,
  });
}

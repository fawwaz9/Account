import { post } from "./apiClient";

/** What the sign-in routes return: a bearer session token. */
interface TokenResponse {
  access_token: string;
  token_type: string;
}

/** Exchange a Google ID token for a session token. */
export function loginWithGoogle(idToken: string) {
  return post<TokenResponse>("auth/google", { id_token: idToken });
}

/** Sign in with email and password. */
export function loginWithEmail(email: string, password: string) {
  return post<TokenResponse>("auth/login", { email, password });
}

/** Create an email-and-password account and sign straight in. */
export function registerWithEmail(name: string, email: string, password: string) {
  return post<TokenResponse>("auth/register", { name, email, password });
}

/**
 * Add or change the signed-in user's password; `currentPassword` only when one exists.
 * Returns a replacement token, since every session is revoked: hand it to AuthContext at once.
 */
export function setPassword(newPassword: string, currentPassword?: string) {
  return post<TokenResponse>("auth/password", {
    new_password: newPassword,
    current_password: currentPassword ?? null,
  });
}

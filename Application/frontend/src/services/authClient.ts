import { post } from "./apiClient"; // adjust path to your actual apiClient location

interface TokenResponse {
  access_token: string;
  token_type: string;
}

export function loginWithGoogle(idToken: string) {
  return post<TokenResponse>("auth/google", { id_token: idToken });
}
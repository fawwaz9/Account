import { get } from "./apiClient";
import { endpoints } from "./endpoints";

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
  auth_provider: "google" | "local";
  email_verified: boolean;
  /** Can sign in with email + password */
  has_password: boolean;
  /** Can sign in with Google */
  has_google: boolean;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return get<CurrentUser>(endpoints.users.me);
}
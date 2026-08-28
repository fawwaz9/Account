import { get } from "./apiClient";
import { endpoints } from "./endpoints";

export interface CurrentUser {
  id: string;
  name: string;
  email: string;
}

export async function getCurrentUser(): Promise<CurrentUser> {
  return get<CurrentUser>(endpoints.users.me);
}
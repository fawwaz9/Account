import { get, post } from "./apiClient";
import { endpoints } from "./endpoints";

const STORAGE_KEY = "account_user_id";
export const DEFAULT_USER = { name: "Account User", email: "account.user@example.com" };

interface UserDetail {
  id: string;
}

async function verifyStoredUserId(stored: string): Promise<boolean> {
  try {
    await get<UserDetail>(endpoints.users.detail(stored));
    return true;
  } catch {
    return false;
  }
}

export async function getOrCreateUserId(): Promise<string> {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored) {
    const valid = await verifyStoredUserId(stored);
    if (valid) {
      return stored;
    }
    localStorage.removeItem(STORAGE_KEY);
  }

  const response = await post<UserDetail>(endpoints.users.base, DEFAULT_USER);
  const userId = response.id;

  if (!userId) {
    throw new Error("User creation failed: no id returned");
  }

  localStorage.setItem(STORAGE_KEY, userId);
  return userId;
}

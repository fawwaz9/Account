import { afterEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
vi.mock("../../services/apiClient", () => ({ get: vi.fn(), post: (...a: unknown[]) => post(...a) }));

import { sendTestPush } from "./push";
import { endpoints } from "../../services/endpoints";

function deviceSubscribedAt(endpoint: string | null) {
  const registration = {
    pushManager: { getSubscription: async () => (endpoint ? { endpoint } : null) },
  };
  Object.defineProperty(navigator, "serviceWorker", {
    configurable: true,
    value: { getRegistration: async () => registration },
  });
}

afterEach(() => {
  post.mockReset();
  Reflect.deleteProperty(navigator, "serviceWorker");
});

describe("sendTestPush", () => {
  it("names this device, so the test arrives here and nowhere else", async () => {
    deviceSubscribedAt("https://push.example/laptop");
    post.mockResolvedValue({ sent: 1 });
    await sendTestPush("u1");
    expect(post).toHaveBeenCalledWith(endpoints.push.test("u1"), { endpoint: "https://push.example/laptop" });
  });
});

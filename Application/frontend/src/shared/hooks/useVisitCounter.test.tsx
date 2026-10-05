// @vitest-environment jsdom
import { cleanup, render } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn().mockResolvedValue(null);
vi.mock("../../services/apiClient", () => ({ post: (...args: unknown[]) => post(...args) }));
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import { moduleFor, useVisitCounter } from "./useVisitCounter";

function Probe() {
  useVisitCounter();
  return null;
}

function visit(path: string) {
  return render(<MemoryRouter initialEntries={[path]}><Probe /></MemoryRouter>);
}

function installSessionStorage() {
  const data = new Map<string, string>();
  Object.defineProperty(window, "sessionStorage", {
    configurable: true,
    value: {
      getItem: (k: string) => data.get(k) ?? null,
      setItem: (k: string, v: string) => void data.set(k, v),
      removeItem: (k: string) => void data.delete(k),
      clear: () => data.clear(),
    },
  });
}

beforeEach(() => {
  post.mockClear();
  installSessionStorage();
});
afterEach(cleanup);

describe("moduleFor", () => {
  it("names the room a path is in, and nothing else", () => {
    expect(moduleFor("/")).toBe("dashboard");
    expect(moduleFor("/grades/courses/abc")).toBe("grades");
    expect(moduleFor("/budget/accounts/x")).toBe("budget");
    expect(moduleFor("/login")).toBeNull();
  });
});

describe("useVisitCounter", () => {
  it("counts a room once per day in this tab", () => {
    visit("/grades");
    cleanup();
    visit("/grades/courses/abc");
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith("usage/u1/visits", { module: "grades" });
  });

  it("counts each room separately", () => {
    visit("/grades");
    cleanup();
    visit("/budget");
    expect(post.mock.calls.map((call) => (call[1] as { module: string }).module)).toEqual(["grades", "budget"]);
  });

  it("never lets a failed count surface", async () => {
    post.mockRejectedValueOnce(new Error("offline"));
    expect(() => visit("/tasks")).not.toThrow();
    await Promise.resolve();
  });
});

describe("visits a notification caused", () => {
  afterEach(() => window.history.replaceState(null, "", "/"));

  it("are counted as prompted, and the marker leaves the address bar", () => {
    window.history.replaceState(null, "", "/tasks?from=push");
    visit("/tasks");
    expect(post).toHaveBeenCalledWith("usage/u1/visits", { module: "tasks", prompted: true });
    expect(window.location.search).toBe("");
  });

  it("stay prompted for the window, then an unprompted visit still counts", async () => {
    const { isPrompted } = await import("../utils/promptedSession");
    window.history.replaceState(null, "", "/tasks?from=push");
    visit("/tasks");
    cleanup();
    visit("/tasks");
    expect(post).toHaveBeenCalledTimes(1); // same tab, same day, still prompted

    expect(isPrompted(Date.now() + 31 * 60 * 1000)).toBe(false);
    window.sessionStorage.removeItem("account.prompted.until"); // the half hour has passed
    cleanup();
    visit("/tasks");
    expect(post).toHaveBeenCalledTimes(2);
    expect(post).toHaveBeenLastCalledWith("usage/u1/visits", { module: "tasks" });
  });
});

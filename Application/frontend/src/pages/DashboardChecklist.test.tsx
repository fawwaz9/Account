// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The checklist is a claim about what exists, so it may not appear until every
 * source behind it has answered -- and answered successfully. A slow budget
 * read showing "Record some money" to someone with a full ledger is exactly the
 * empty-state-while-loading fault the owner reported on the Tasks page.
 */

const state = {
  dashboard: { summary: { total_courses: 0 } as unknown, loading: false, error: null as string | null },
  budget: { accounts: [] as unknown[], summary: { total_actual: 0, total_planned: 0, by_category: [] } as unknown,
    totalBalance: 0, error: null as string | null, loaded: true },
  time: { blocks: [], load: { booked_minutes: 0, task_count: 0, estimated_minutes: 0 } as unknown, loaded: true },
};

vi.mock("../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "u1", name: "New", current_school_year: null, current_semester: null,
    preferences: { timezone: "America/Regina" } } }),
}));
vi.mock("../features/grades/hooks/useDashboard", () => ({ useDashboard: () => state.dashboard }));
vi.mock("../features/budget/hooks/useBudgetGlance", () => ({ useBudgetGlance: () => state.budget }));
vi.mock("../features/calender/hooks/useTimeGlance", () => ({ useTimeGlance: () => state.time }));
vi.mock("../features/calender/hooks/useWorkloadForecast", () => ({ useWorkloadForecast: () => null }));
vi.mock("../features/survey/DisappointmentQuestion", () => ({ default: () => null }));

import Dashboard from "./Dashboard";

function show() {
  return render(<MemoryRouter><Dashboard /></MemoryRouter>);
}

beforeEach(() => {
  installStorage();
  state.dashboard = { summary: { total_courses: 0 }, loading: false, error: null };
  state.budget = { ...state.budget, error: null, loaded: true };
  state.time = { ...state.time, loaded: true };
});
afterEach(cleanup);

/** jsdom under this Node has no usable localStorage; a fresh in-memory one per test. */
function installStorage() {
  const data = new Map<string, string>();
  const storage = {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, String(value)),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: (index: number) => [...data.keys()][index] ?? null,
    get length() { return data.size; },
  };
  Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
}


describe("the dashboard checklist", () => {
  it("shows for a new account once everything has loaded", () => {
    show();
    expect(screen.getByRole("heading", { name: /Get started/ })).toBeTruthy();
  });

  it("waits while the grades summary is loading", () => {
    state.dashboard = { summary: null, loading: true, error: null };
    show();
    expect(screen.queryByRole("heading", { name: /Get started/ })).toBeNull();
  });

  it("waits while the budget has not answered", () => {
    state.budget = { ...state.budget, loaded: false };
    show();
    expect(screen.queryByRole("heading", { name: /Get started/ })).toBeNull();
  });

  it("stays away when the week could not be read", () => {
    state.time = { ...state.time, loaded: false };
    show();
    expect(screen.queryByRole("heading", { name: /Get started/ })).toBeNull();
  });
});

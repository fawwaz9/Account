// @vitest-environment jsdom
import { renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The window of shifts the Jobs page reads: back 90 days, so a past shift
 * nobody confirmed stays in the list until it is (shiftOrder.ts), and three
 * weeks ahead.
 */

const { fetchShifts } = vi.hoisted(() => ({ fetchShifts: vi.fn() }));
vi.mock("../api", () => ({
  fetchShifts,
  fetchJobs: vi.fn().mockResolvedValue([]),
  fetchPaycheques: vi.fn().mockResolvedValue([]),
  fetchEarnings: vi.fn().mockResolvedValue(null),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("../../../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../../shared/utils/dateUtils")>()),
  today: () => "2026-10-12",
}));

import { useJobs } from "./useJobs";

beforeEach(() => fetchShifts.mockResolvedValue([]));
afterEach(() => vi.clearAllMocks());

describe("the shift window", () => {
  it("reaches back 90 days and ahead 21", async () => {
    renderHook(() => useJobs(false));
    await waitFor(() => expect(fetchShifts).toHaveBeenCalledWith("u1", "2026-07-14", "2026-11-02"));
  });
});

// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor } from "@testing-library/react";

const api = { fetchWeekLoad: vi.fn(), fetchFreeBlocks: vi.fn() };
vi.mock("../api", () => ({
  fetchWeekLoad: (...a: unknown[]) => api.fetchWeekLoad(...a),
  fetchFreeBlocks: (...a: unknown[]) => api.fetchFreeBlocks(...a),
}));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import { useWorkloadForecast } from "./useWorkloadForecast";
import { addDays, today } from "../../../shared/utils/dateUtils";

beforeEach(() => {
  api.fetchWeekLoad.mockReset();
  api.fetchFreeBlocks.mockReset();
});
afterEach(cleanup);

describe("useWorkloadForecast", () => {
  it("reads today and the six days after, and adds up every free block", async () => {
    api.fetchWeekLoad.mockResolvedValue({ estimated_minutes: 300, task_count: 4, unestimated_tasks: 1 });
    api.fetchFreeBlocks.mockResolvedValue([{ minutes: 120 }, { minutes: 45 }, { minutes: 90 }]);
    const { result } = renderHook(() => useWorkloadForecast());
    await waitFor(() => expect(result.current).not.toBeNull());
    expect(result.current).toEqual({
      estimatedMinutes: 300, taskCount: 4, unestimatedTasks: 1, freeMinutes: 255,
      // Not scaled: the load carried no ratio, and the typed total is the figure.
      estimateRatio: null, typedMinutes: 300,
    });
    const window = ["u1", today(), addDays(today(), 6)];
    expect(api.fetchWeekLoad).toHaveBeenCalledWith(...window);
    expect(api.fetchFreeBlocks).toHaveBeenCalledWith(...window);
  });

  it("stays null when either read fails, so a failure never reads as nothing due", async () => {
    api.fetchWeekLoad.mockResolvedValue({ estimated_minutes: 0, task_count: 0, unestimated_tasks: 0 });
    api.fetchFreeBlocks.mockRejectedValue(new Error("500"));
    const { result } = renderHook(() => useWorkloadForecast());
    await waitFor(() => expect(api.fetchFreeBlocks).toHaveBeenCalled());
    await Promise.resolve();
    expect(result.current).toBeNull();
  });
});

// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Job, JobKind } from "../types";

/** The job form sends a repeat or set days of the month, never both. */

const { updateJob } = vi.hoisted(() => ({ updateJob: vi.fn() }));
vi.mock("../api", () => ({ updateJob, createJob: vi.fn(), deleteJob: vi.fn() }));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import JobModal from "./JobModal";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const JOB: Job = {
  id: "j1", name: "Bookstore", employer: null, kind: JobKind.SALARIED, hourly_rate: null, period_amount: 1500,
  started_on: "2026-09-01", ended_on: null, pay_starts_on: "2026-09-15",
  pay_schedule: { freq: "weekly", interval: 2, byday: ["TU"], until: null, count: null },
  pay_days: null, archived: false, position: 0, created_at: null, next_pay_on: null, is_current: true,
};

function show(job: Job) {
  render(<JobModal open job={job} onClose={() => {}} onSaved={() => {}} />);
}

describe("the job form's pay schedule", () => {
  it("switching to set days clears the repeat and sends the days", async () => {
    updateJob.mockResolvedValue({});
    show(JOB);
    fireEvent.click(screen.getByRole("radio", { name: "Set days of the month" }));
    fireEvent.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() => expect(updateJob).toHaveBeenCalled());
    const payload = updateJob.mock.calls[0][2];
    expect(payload.pay_schedule).toBeNull();
    expect(payload.pay_days).toEqual({ dates: [15], last_day: false, nth_weekdays: [], weekend: "previous", until: null });
  });

  it("opens a days-of-the-month job on its days, and switching back sends no days", async () => {
    updateJob.mockResolvedValue({});
    show({ ...JOB, pay_schedule: null,
      pay_days: { dates: [15], last_day: true, nth_weekdays: [], weekend: "previous", until: null } });
    expect((screen.getByRole("radio", { name: "Set days of the month" }) as HTMLInputElement).checked).toBe(true);
    fireEvent.click(screen.getByRole("radio", { name: "A repeat" }));
    fireEvent.click(screen.getByRole("button", { name: "Save job" }));
    await waitFor(() => expect(updateJob).toHaveBeenCalled());
    expect(updateJob.mock.calls[0][2].pay_days).toBeNull();
  });
});

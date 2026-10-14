// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Application, ApplicationStats } from "../features/jobs/applications/types";

/** The tracker page (Phase 3 item 1): figures, the lists, and "no reply yet?" (D3). */

const { fetchApplications, fetchApplicationStats, addStep, fetchSeasons } = vi.hoisted(() => ({
  fetchApplications: vi.fn(), fetchApplicationStats: vi.fn(), addStep: vi.fn(), fetchSeasons: vi.fn(),
}));
vi.mock("../features/jobs/applications/api", () => ({
  fetchApplications, fetchApplicationStats, addStep, fetchSeasons,
  createSeason: vi.fn(), updateSeason: vi.fn(), deleteSeason: vi.fn(),
  createApplication: vi.fn(), updateApplication: vi.fn(), deleteApplication: vi.fn(), deleteStep: vi.fn(),
}));
vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../shared/utils/dateUtils")>()),
  today: () => "2026-10-12",
}));

import ApplicationsPage from "./ApplicationsPage";

function application(over: Partial<Application>): Application {
  return {
    id: "a1", company: "Shopify", role: "Backend intern", applied_on: "2026-08-01", source: null, link: null,
    location: null, notes: null, status: "applied", deadline: null, follow_up_on: null, offer_amount: null,
    offer_period: null, steps: [], last_step_on: "2026-08-01", quiet: false, created_at: null, updated_at: null,
    ...over,
  };
}

const STATS: ApplicationStats = {
  total: 3, open: 2, replied: 1, reply_rate: 0.333, median_days_to_reply: 9, interviews: 1, offers: 0, accepted: 0,
  by_status: {}, flows: [{ source: "applied", target: "waiting", count: 2 }, { source: "applied", target: "rejected", count: 1 }],
};

function show() {
  return render(<MemoryRouter initialEntries={["/jobs/applications"]}><ApplicationsPage /></MemoryRouter>);
}

beforeEach(() => {
  fetchApplications.mockResolvedValue([
    application({ id: "a1", company: "Quiet Co", quiet: true }),
    application({ id: "a2", company: "Busy Co", status: "interview" }),
    application({ id: "a3", company: "Done Co", status: "rejected" }),
  ]);
  fetchApplicationStats.mockResolvedValue(STATS);
  addStep.mockResolvedValue({});
  fetchSeasons.mockResolvedValue([]);
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("the tracker page", () => {
  it("shows your figures from the server", async () => {
    show();
    expect(await screen.findByText("33%")).toBeTruthy();
    expect(screen.getByText("Heard back")).toBeTruthy();
    expect(screen.getByText("9d")).toBeTruthy();
  });

  it("splits what is in progress from what is finished", async () => {
    show();
    await screen.findByText("Quiet Co");
    const inProgress = screen.getByRole("heading", { name: "In progress" }).parentElement!;
    const finished = screen.getByRole("heading", { name: "Finished" }).parentElement!;
    expect(inProgress.textContent).toContain("Busy Co");
    expect(finished.textContent).toContain("Done Co");
    expect(inProgress.textContent).not.toContain("Done Co");
  });

  it("asks 'no reply yet?' on a quiet one only, and marks it on a tap (D3)", async () => {
    show();
    await screen.findByText("Quiet Co");
    const buttons = screen.getAllByRole("button", { name: "Mark no reply" });
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    await waitFor(() => expect(addStep).toHaveBeenCalledWith("u1", "a1", { status: "no_reply", on_date: "2026-10-12", note: null }));
  });

  it("draws the Sankey with its numbers in words", async () => {
    show();
    expect(await screen.findByRole("img", { name: "Applied to Waiting: 2; Applied to Rejected: 1" })).toBeTruthy();
  });

  it("says nothing is there only once it has loaded", async () => {
    fetchApplications.mockReturnValue(new Promise(() => {}));
    show();
    expect(screen.getByRole("status").textContent).toBe("Loading…");
    expect(screen.queryByText(/No applications yet/)).toBeNull();
  });

  it("invites the first application when there are none", async () => {
    fetchApplications.mockResolvedValue([]);
    fetchApplicationStats.mockResolvedValue({ ...STATS, total: 0, flows: [] });
    show();
    expect(await screen.findByText(/No applications yet/)).toBeTruthy();
  });

  it("sits under Jobs, with both tabs", async () => {
    show();
    await screen.findByText("Quiet Co");
    expect(screen.getByRole("link", { name: "Applications" }).getAttribute("aria-current")).toBe("page");
    expect(screen.getByRole("link", { name: "Jobs" }).getAttribute("href")).toBe("/jobs");
  });
});

describe("seasons (D7)", () => {
  const SEASONS = [
    { id: "fall", name: "Fall 2026 co-op", starts: "2026-09", ends: "2026-12" },
    { id: "summer", name: "Summer 2026", starts: "2026-05", ends: "2026-08" },
  ];

  it("opens on the season you're in, and asks for that season's data", async () => {
    fetchSeasons.mockResolvedValue(SEASONS);
    show();
    await screen.findByText("Quiet Co");
    expect((screen.getByLabelText("Season") as HTMLSelectElement).value).toBe("fall");
    expect(fetchApplications).toHaveBeenLastCalledWith("u1", "fall");
    expect(fetchApplicationStats).toHaveBeenLastCalledWith("u1", "fall");
  });

  it("refetches everything for another season, and for all time", async () => {
    fetchSeasons.mockResolvedValue(SEASONS);
    show();
    await screen.findByText("Quiet Co");
    fireEvent.change(screen.getByLabelText("Season"), { target: { value: "summer" } });
    await waitFor(() => expect(fetchApplicationStats).toHaveBeenLastCalledWith("u1", "summer"));
    expect(fetchApplications).toHaveBeenLastCalledWith("u1", "summer");
    fireEvent.change(screen.getByLabelText("Season"), { target: { value: "all" } });
    await waitFor(() => expect(fetchApplications).toHaveBeenLastCalledWith("u1", null));
  });

  it("says a season is empty in its own words", async () => {
    fetchSeasons.mockResolvedValue(SEASONS);
    fetchApplications.mockResolvedValue([]);
    fetchApplicationStats.mockResolvedValue({ ...STATS, total: 0, flows: [] });
    show();
    expect(await screen.findByText("Nothing applied for in Fall 2026 co-op (Sep 2026 – Dec 2026) yet.")).toBeTruthy();
  });

  it("shows all time, and offers a first season, when there are none", async () => {
    show();
    await screen.findByText("Quiet Co");
    expect((screen.getByLabelText("Season") as HTMLSelectElement).value).toBe("all");
    expect(fetchApplications).toHaveBeenLastCalledWith("u1", null);
    expect(screen.getByRole("button", { name: "Add a season" })).toBeTruthy();
  });

  it("does not fetch before it knows which season to show", () => {
    fetchSeasons.mockReturnValue(new Promise(() => {}));
    show();
    expect(fetchApplications).not.toHaveBeenCalled();
  });
});

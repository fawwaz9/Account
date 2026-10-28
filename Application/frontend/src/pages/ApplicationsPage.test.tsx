// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Application, ApplicationStats } from "../features/jobs/applications/types";

/** The tracker page (Phase 3 item 1): figures, what needs you (D9), search, and "no reply yet?" (D3). */

const { fetchApplications, fetchApplicationStats, addStep, fetchSeasons } = vi.hoisted(() => ({
  fetchApplications: vi.fn(), fetchApplicationStats: vi.fn(), addStep: vi.fn(), fetchSeasons: vi.fn(),
}));
vi.mock("../features/jobs/applications/api", () => ({
  fetchApplications, fetchApplicationStats, addStep, fetchSeasons,
  createSeason: vi.fn(), updateSeason: vi.fn(), deleteSeason: vi.fn(),
  createApplication: vi.fn(), updateApplication: vi.fn(), deleteApplication: vi.fn(), deleteStep: vi.fn(),
  setSalaryShare: vi.fn(), fetchSalaries: () => Promise.resolve([]),
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
    offer_period: null, steps: [], last_step_on: "2026-08-01", quiet: false, salary_shared: false, created_at: null, updated_at: null,
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
    application({ id: "a4", company: "New Co", applied_on: "2026-10-01", last_step_on: "2026-10-01" }),
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

  it("lists what needs you and the quiet ones, and nothing else until asked (D9)", async () => {
    show();
    await screen.findByText("Quiet Co");
    const needsYou = screen.getByRole("heading", { name: "Needs you" }).parentElement!;
    const quiet = screen.getByRole("heading", { name: "No reply yet?" }).closest("section")!;
    expect(needsYou.textContent).toContain("Busy Co");
    expect(quiet.textContent).toContain("Quiet Co");
    expect(screen.queryByText("Done Co")).toBeNull();
    expect(screen.queryByText("New Co")).toBeNull();
  });

  it("shows waiting and finished on a tap, and hides them again", async () => {
    show();
    await screen.findByText("Quiet Co");
    fireEvent.click(screen.getByRole("button", { name: "Show finished (1)" }));
    expect(screen.getByRole("heading", { name: "Finished" }).parentElement!.textContent).toContain("Done Co");
    expect(screen.queryByText("New Co")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show waiting (1)" }));
    expect(screen.getByRole("heading", { name: "Waiting to hear back" }).parentElement!.textContent).toContain("New Co");
    fireEvent.click(screen.getByRole("button", { name: "Hide finished" }));
    expect(screen.queryByText("Done Co")).toBeNull();
  });

  it("finds any application by search, finished ones included, in place of the lists", async () => {
    show();
    await screen.findByText("Quiet Co");
    fireEvent.change(screen.getByLabelText("Find an application"), { target: { value: "done" } });
    const results = screen.getByRole("region", { name: "Search results" });
    expect(results.textContent).toContain("1 match");
    expect(results.textContent).toContain("Done Co");
    expect(screen.queryByText("Busy Co")).toBeNull();
    expect(screen.queryByRole("heading", { name: "Needs you" })).toBeNull();
  });

  it("says when nothing matches, and the lists come back once the search is cleared", async () => {
    show();
    await screen.findByText("Quiet Co");
    const search = screen.getByLabelText("Find an application");
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("0 matches")).toBeTruthy();
    expect(screen.getByText(/Nothing matches “zzz”/)).toBeTruthy();
    fireEvent.change(search, { target: { value: "" } });
    expect(screen.getByRole("heading", { name: "Needs you" })).toBeTruthy();
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
    expect(await screen.findByRole("img", {
      name: "Applied to Waiting: 2; Applied to Rejected: 1; In all: Waiting 2 · Rejected 1",
    })).toBeTruthy();
    // Outcomes are named for what they are, not for their stage-qualified id (D8).
    expect(screen.getByText("Rejected 1", { selector: "text" })).toBeTruthy();
    expect(screen.queryByText(/@/)).toBeNull();
    expect(screen.getByText("In all: Waiting 2 · Rejected 1")).toBeTruthy();
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

describe("marking every quiet one (D9)", () => {
  const QUIET = [
    application({ id: "q1", company: "Quiet One", quiet: true }),
    application({ id: "q2", company: "Quiet Two", quiet: true }),
    application({ id: "q3", company: "Quiet Three", quiet: true }),
  ];

  it("asks first, then marks each one no reply", async () => {
    fetchApplications.mockResolvedValue(QUIET);
    show();
    await screen.findByText("Quiet One");
    fireEvent.click(screen.getByRole("button", { name: "Mark all 3 as no reply" }));
    expect(addStep).not.toHaveBeenCalled();
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark 3 as no reply" }));
    await waitFor(() => expect(addStep).toHaveBeenCalledTimes(3));
    for (const id of ["q1", "q2", "q3"]) {
      expect(addStep).toHaveBeenCalledWith("u1", id, { status: "no_reply", on_date: "2026-10-12", note: null });
    }
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("marks nothing when cancelled", async () => {
    fetchApplications.mockResolvedValue(QUIET);
    show();
    await screen.findByText("Quiet One");
    fireEvent.click(screen.getByRole("button", { name: "Mark all 3 as no reply" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(addStep).not.toHaveBeenCalled();
  });

  it("says how far it got when one fails, and stops there", async () => {
    fetchApplications.mockResolvedValue(QUIET);
    addStep.mockResolvedValueOnce({}).mockRejectedValueOnce(new Error("Network down"));
    show();
    await screen.findByText("Quiet One");
    fireEvent.click(screen.getByRole("button", { name: "Mark all 3 as no reply" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark 3 as no reply" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Marked 1 of 3 as no reply, then stopped: Network down");
    expect(addStep).toHaveBeenCalledTimes(2);
  });

  it("offers no 'mark all' for a single quiet one", async () => {
    show();
    await screen.findByText("Quiet Co");
    expect(screen.queryByRole("button", { name: /Mark all/ })).toBeNull();
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

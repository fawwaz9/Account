// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const api = vi.hoisted(() => ({
  fetchTeams: vi.fn(), fetchTeam: vi.fn(), createTeam: vi.fn(), renameTeam: vi.fn(), removeTeam: vi.fn(),
  makeTeamLink: vi.fn(), cancelTeamLink: vi.fn(), removeTeamMember: vi.fn(), leaveTeam: vi.fn(),
  recordGame: vi.fn(), correctGame: vi.fn(), confirmGame: vi.fn(), disputeGame: vi.fn(), removeGame: vi.fn(),
  previewTeamInvite: vi.fn(), acceptTeamInvite: vi.fn(),
}));
vi.mock("../features/teams/api", async () => {
  const real = await vi.importActual<typeof import("../features/teams/api")>("../features/teams/api");
  const mocked: Record<string, unknown> = {};
  for (const name of Object.keys(api) as (keyof typeof api)[]) {
    mocked[name] = (...a: unknown[]) => api[name](...a);
  }
  return { ...real, ...mocked };
});
vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
// The cards beyond teams (Phase 3) have tests of their own; here they stay quiet.
vi.mock("../features/teams/fitnessApi", () => ({
  fetchGymBuddies: () => Promise.reject(new Error("not under test")),
  saveGymBuddy: vi.fn(),
}));

import FitnessPage from "./FitnessPage";
import InvitePage from "./InvitePage";
import { recordLine, teamInviteLink } from "../features/teams/api";
import { today } from "../shared/utils/dateUtils";

/** Phase 2 item 11 (D26): teams and games. */

const record = { wins: 2, losses: 1, ties: 0, points_for: 21, points_against: 15, unconfirmed: 1 };
const summary = { team_id: "t1", name: "Thunder", sport: "Ultimate", captain_name: "Sam", is_captain: false,
                  member_names: ["Alex", "Kim"], record };
const game = (over: Record<string, unknown> = {}) => ({
  game_id: "g1", played_on: "2026-10-08", opponent: "Lightning", our_score: 7, their_score: 5,
  recorded_by_name: "Kim", recorded_by_me: false, confirmed_by_name: null, confirmed_at: null,
  disputed_by_name: null, disputed_by_me: false, disputed_our: null, disputed_their: null, ...over,
});
const detail = (over: Record<string, unknown> = {}) => ({ ...summary, games: [game()], members: null, link: null, ...over });

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

async function openTeam(team = detail()) {
  api.fetchTeams.mockResolvedValue([summary]);
  api.fetchTeam.mockResolvedValue(team);
  render(<FitnessPage />);
  return screen.findByRole("region", { name: "Thunder" });
}

describe("FitnessPage", () => {
  it("lists your teams with their records, and says what to do with none", async () => {
    api.fetchTeams.mockResolvedValue([]);
    render(<FitnessPage />);
    expect(await screen.findByText(/No teams yet/)).toBeTruthy();
    cleanup();
    await openTeam();
    expect(screen.getAllByText("2–1–0").length).toBeGreaterThan(0);
    expect(screen.getByText(/1 waiting to be confirmed/)).toBeTruthy();
  });

  it("makes a team", async () => {
    api.fetchTeams.mockResolvedValue([]);
    api.createTeam.mockResolvedValue({ ...detail(), team_id: "t2" });
    render(<FitnessPage />);
    fireEvent.change(await screen.findByLabelText("New team name"), { target: { value: " Thunder " } });
    fireEvent.change(screen.getByLabelText("New team sport"), { target: { value: "Ultimate" } });
    fireEvent.click(screen.getByRole("button", { name: "New team" }));
    await waitFor(() => expect(api.createTeam).toHaveBeenCalledWith("u1", "Thunder", "Ultimate"));
  });

  it("records a game in one form, with today already filled in", async () => {
    api.recordGame.mockResolvedValue(detail());
    const view = await openTeam();
    const form = within(view).getByRole("form", { name: "Record the game" });
    expect((within(form).getByLabelText("Date played") as HTMLInputElement).value).toBe(today());
    fireEvent.change(within(form).getByLabelText("Opponent"), { target: { value: "Storm" } });
    fireEvent.change(within(form).getByLabelText("Our score"), { target: { value: "9" } });
    fireEvent.change(within(form).getByLabelText("Their score"), { target: { value: "4" } });
    fireEvent.click(within(form).getByRole("button", { name: "Record the game" }));
    await waitFor(() => expect(api.recordGame).toHaveBeenCalledWith("u1", "t1",
      { played_on: today(), opponent: "Storm", our_score: 9, their_score: 4 }));
  });

  it("offers confirm and dispute on someone else's game, never on your own", async () => {
    api.confirmGame.mockResolvedValue({ ok: true });
    const view = await openTeam();
    expect(within(view).getByText(/waiting for someone else to confirm/)).toBeTruthy();
    expect(within(view).queryByRole("button", { name: "Correct" })).toBeNull();
    fireEvent.click(within(view).getByRole("button", { name: "Confirm" }));
    await waitFor(() => expect(api.confirmGame).toHaveBeenCalledWith("u1", "t1", "g1"));
    cleanup();
    const mine = await openTeam(detail({ games: [game({ recorded_by_me: true, recorded_by_name: "Alex" })] }));
    expect(within(mine).queryByRole("button", { name: "Confirm" })).toBeNull();
    expect(within(mine).queryByRole("button", { name: "Dispute" })).toBeNull();
    expect(within(mine).getByRole("button", { name: "Correct" })).toBeTruthy();
  });

  it("shows both scores when disputed, and nobody else may confirm over it", async () => {
    const view = await openTeam(detail({ games: [game({ disputed_by_name: "Alex", disputed_our: 6, disputed_their: 5 })] }));
    expect(within(view).getByText("Disputed by Alex, who says 6–5")).toBeTruthy();
    expect(within(view).queryByRole("button", { name: "Confirm" })).toBeNull();
  });

  it("sends a dispute with the score you saw", async () => {
    api.disputeGame.mockResolvedValue({ ok: true });
    const view = await openTeam();
    fireEvent.click(within(view).getByRole("button", { name: "Dispute" }));
    fireEvent.change(within(view).getByLabelText("Our score, as you saw it"), { target: { value: "6" } });
    fireEvent.click(within(view).getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.disputeGame).toHaveBeenCalledWith("u1", "t1", "g1", 6, 5));
  });

  it("lets the captain delete a confirmed game, after asking", async () => {
    api.removeGame.mockResolvedValue({ ok: true });
    const view = await openTeam(detail({ is_captain: true, members: [], games: [game({ confirmed_by_name: "Alex" })] }));
    expect(within(view).getByText("Confirmed by Alex")).toBeTruthy();
    fireEvent.click(within(view).getByRole("button", { name: "Delete" }));
    expect(api.removeGame).not.toHaveBeenCalled();
    fireEvent.click(within(view).getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(api.removeGame).toHaveBeenCalledWith("u1", "t1", "g1"));
  });

  it("gives the captain a team link and a member a way to leave, each asking first", async () => {
    api.makeTeamLink.mockResolvedValue({ token: "tok_abcdefghijklmnopqrstuv", expires_at: "2026-10-18T00:00:00" });
    const captains = await openTeam(detail({ is_captain: true, members: [] }));
    fireEvent.click(await within(captains).findByRole("button", { name: "Share with a link" }));
    const field = await within(captains).findByLabelText("Team link") as HTMLInputElement;
    expect(field.value).toMatch(/\/invite#team:tok_abcdefghijklmnopqrstuv$/);
    cleanup();
    api.leaveTeam.mockResolvedValue({ left: true });
    const members = await openTeam();
    fireEvent.click(within(members).getByRole("button", { name: "Leave this team" }));
    expect(api.leaveTeam).not.toHaveBeenCalled();
    fireEvent.click(within(members).getByRole("button", { name: "Leave" }));
    await waitFor(() => expect(api.leaveTeam).toHaveBeenCalledWith("u1", "t1"));
  });
});

describe("the page", () => {
  it("is called Fitness, with your teams inside it", async () => {
    api.fetchTeams.mockResolvedValue([]);
    render(<FitnessPage />);
    expect(await screen.findByRole("heading", { level: 1, name: "Fitness" })).toBeTruthy();
    expect(screen.getByRole("heading", { level: 2, name: "Teams" })).toBeTruthy();
  });
});

describe("helpers", () => {
  it("reads a record as wins–losses–ties, and keeps the token out of the path", () => {
    expect(recordLine(record)).toBe("2–1–0");
    expect(teamInviteLink("abc", "https://account-2a7.pages.dev")).toBe("https://account-2a7.pages.dev/invite#team:abc");
  });
});

describe("InvitePage, for a team", () => {
  it("names the captain and the team, and asks before joining", async () => {
    api.previewTeamInvite.mockResolvedValue({ captain_name: "Sam", team_name: "Thunder", sport: "Ultimate" });
    api.acceptTeamInvite.mockResolvedValue({ status: "accepted" });
    render(
      <MemoryRouter initialEntries={["/invite#team:tok_abcdefghijklmnopqrstuv"]}>
        <Routes>
          <Route path="/invite" element={<InvitePage />} />
          <Route path="/fitness" element={<p>fitness page</p>} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Thunder")).toBeTruthy();
    expect(api.acceptTeamInvite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Join the team" }));
    expect(await screen.findByText("fitness page")).toBeTruthy();
    expect(api.acceptTeamInvite).toHaveBeenCalledWith("u1", "tok_abcdefghijklmnopqrstuv");
  });
});

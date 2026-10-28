// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  fetchTeamBoard: vi.fn(), fetchCampusBoard: vi.fn(), fetchDirectory: vi.fn(), joinTeam: vi.fn(),
  fetchMyJoinRequests: vi.fn(), withdrawJoinRequest: vi.fn(), fetchTeamJoinRequests: vi.fn(),
  answerJoinRequest: vi.fn(),
}));
vi.mock("./api", () => api);
const teamsApi = { updateTeamListing: vi.fn() };
vi.mock("../teams/api", () => ({ updateTeamListing: (...a: unknown[]) => teamsApi.updateTeamListing(...a) }));
const prefs = { updatePreferences: vi.fn() };
vi.mock("../../services/currentUserClient", () => ({
  updatePreferences: (...a: unknown[]) => prefs.updatePreferences(...a),
}));
const refreshUser = vi.fn();
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" }, refreshUser }) }));

import TeamBoard from "./TeamBoard";
import TeamListingForm from "./TeamListingForm";
import TeamRequests from "./TeamRequests";
import CampusBoardCard from "./CampusBoardCard";
import DirectoryCard from "./DirectoryCard";
import { DirectoryTeam } from "./api";

/** Phase 3 items 8-9: team and campus boards, listing, requests and the directory (D13). */

beforeEach(() => {
  [...Object.values(api), teamsApi.updateTeamListing, prefs.updatePreferences, refreshUser].forEach((fn) => fn.mockReset());
});
afterEach(cleanup);

function team(over: Partial<DirectoryTeam>): DirectoryTeam {
  return {
    team_id: "t1", name: "Disc Jockeys", sport: "Ultimate", level: "casual", area: "UBC", looking: true,
    blurb: "Tuesdays", members: 7, last_game_on: "2026-10-20", dormant: false, mine: false, requested: null, ...over,
  };
}

describe("TeamBoard", () => {
  it("shows opted-in teammates once you've opted in", async () => {
    api.fetchTeamBoard.mockResolvedValue({
      opted_in: true, week_start: "2026-10-26",
      rows: [{ name: "Alex", points: 80, is_me: false }, { name: "Sam", points: 50, is_me: true }],
    });
    render(<TeamBoard userId="u1" teamId="t1" />);
    const items = (await screen.findAllByRole("listitem")).map((li) => li.textContent);
    expect(items).toEqual(["Alex80", "Sam (you)50"]);
  });

  it("opts in, then reads the board again", async () => {
    api.fetchTeamBoard.mockResolvedValueOnce({ opted_in: false, week_start: "2026-10-26", rows: [] })
      .mockResolvedValueOnce({ opted_in: true, week_start: "2026-10-26", rows: [] });
    prefs.updatePreferences.mockResolvedValue({});
    render(<TeamBoard userId="u1" teamId="t1" />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Show my points on team boards" }));
    await waitFor(() => expect(prefs.updatePreferences).toHaveBeenCalledWith("u1", { leaderboard_opt_in: true }));
    expect(await screen.findByText("No points logged this week yet.")).toBeTruthy();
    expect(refreshUser).toHaveBeenCalled();
  });
});

describe("TeamListingForm", () => {
  it("saves the listing with blanks as nothing", async () => {
    teamsApi.updateTeamListing.mockResolvedValue({});
    const onSaved = vi.fn();
    render(<TeamListingForm userId="u1" teamId="t1" onSaved={onSaved}
      listing={{ listed: false, level: null, area: null, looking_for_players: false, blurb: null }} />);
    fireEvent.click(screen.getByRole("checkbox", { name: "List this team on campus" }));
    fireEvent.change(screen.getByLabelText("Level"), { target: { value: "competitive" } });
    fireEvent.change(screen.getByLabelText("Where you play"), { target: { value: " Kits " } });
    fireEvent.click(screen.getByRole("button", { name: "Save listing" }));
    await waitFor(() => expect(teamsApi.updateTeamListing).toHaveBeenCalledWith("u1", "t1", {
      listed: true, level: "competitive", area: "Kits", looking_for_players: false, blurb: null,
    }));
    expect(onSaved).toHaveBeenCalled();
  });
});

describe("TeamRequests", () => {
  it("lists who asked and accepts one", async () => {
    api.fetchTeamJoinRequests.mockResolvedValueOnce([
      { request_id: "r1", requester_name: "Jo", message: "I can play Tuesdays", created_at: "x" },
    ]).mockResolvedValueOnce([]);
    api.answerJoinRequest.mockResolvedValue({ status: "accepted" });
    const onChanged = vi.fn();
    render(<TeamRequests userId="u1" teamId="t1" onChanged={onChanged} />);
    expect((await screen.findByRole("listitem")).textContent).toMatch(/Jo · I can play Tuesdays/);
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(api.answerJoinRequest).toHaveBeenCalledWith("u1", "r1", true);
  });

  it("is silent when nobody has asked", async () => {
    api.fetchTeamJoinRequests.mockResolvedValue([]);
    const { container } = render(<TeamRequests userId="u1" teamId="t1" onChanged={vi.fn()} />);
    await waitFor(() => expect(api.fetchTeamJoinRequests).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("CampusBoardCard", () => {
  it("ranks listed teams, or says when it opens", async () => {
    api.fetchCampusBoard.mockResolvedValue({ floor: 5, week_start: "2026-10-26",
      teams: [{ team_name: "Disc Jockeys", sport: "Ultimate", points: 120 }] });
    render(<CampusBoardCard userId="u1" />);
    expect((await screen.findByRole("listitem")).textContent).toBe("Disc Jockeys · Ultimate120");
    cleanup();
    api.fetchCampusBoard.mockResolvedValue({ floor: 5, week_start: null, teams: [] });
    render(<CampusBoardCard userId="u1" />);
    expect(await screen.findByText("Opens once 5 teams are listed on campus.")).toBeTruthy();
  });
});

describe("DirectoryCard", () => {
  it("asks to join with a message and shows the request", async () => {
    api.fetchDirectory.mockResolvedValueOnce({ floor: 5, teams: [team({})] })
      .mockResolvedValueOnce({ floor: 5, teams: [team({ requested: "pending" })] });
    api.fetchMyJoinRequests.mockResolvedValueOnce([]).mockResolvedValueOnce([
      { id: "r1", team_name: "Disc Jockeys", message: "hi", status: "pending", created_at: "x" }]);
    api.joinTeam.mockResolvedValue({ status: "sent" });
    render(<DirectoryCard userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask to join" }));
    fireEvent.change(screen.getByLabelText("Message for Disc Jockeys"), { target: { value: " hi " } });
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(api.joinTeam).toHaveBeenCalledWith("u1", "t1", "hi"));
    expect(await screen.findByText(/The captain sees your name and message/)).toBeTruthy();
    expect(await screen.findByText("Asked: waiting")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Take back" })).toBeTruthy();
  });

  it("says why a request was refused", async () => {
    api.fetchDirectory.mockResolvedValue({ floor: 5, teams: [team({})] });
    api.fetchMyJoinRequests.mockResolvedValue([]);
    api.joinTeam.mockResolvedValue({ status: "limit" });
    render(<DirectoryCard userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Ask to join" }));
    fireEvent.click(screen.getByRole("button", { name: "Send" }));
    expect(await screen.findByText(/You have 5 requests waiting/)).toBeTruthy();
  });

  it("filters by sport and greys dormant teams", async () => {
    api.fetchDirectory.mockResolvedValue({ floor: 5, teams: [
      team({ team_id: "a", name: "A", sport: "Ultimate" }),
      team({ team_id: "b", name: "B", sport: "Volleyball", dormant: true }),
    ] });
    api.fetchMyJoinRequests.mockResolvedValue([]);
    render(<DirectoryCard userId="u1" />);
    const list = await screen.findByRole("list");
    expect(within(list).getAllByRole("listitem")[1].className).toBe("directoryDormant");
    fireEvent.change(screen.getByLabelText("Sport"), { target: { value: "Volleyball" } });
    expect(within(screen.getByRole("list")).getAllByRole("listitem").map((li) => li.textContent?.slice(0, 1)))
      .toEqual(["B"]);
  });

  it("says when it opens, and never offers to join your own team", async () => {
    api.fetchDirectory.mockResolvedValue({ floor: 5, teams: [] });
    api.fetchMyJoinRequests.mockResolvedValue([]);
    render(<DirectoryCard userId="u1" />);
    expect(await screen.findByText("Opens once 5 teams are listed on campus.")).toBeTruthy();
    cleanup();
    api.fetchDirectory.mockResolvedValue({ floor: 5, teams: [team({ mine: true })] });
    render(<DirectoryCard userId="u1" />);
    expect(await screen.findByText("Your team")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Ask to join" })).toBeNull();
  });
});

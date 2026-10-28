// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = vi.hoisted(() => ({
  fetchClubs: vi.fn(), fetchClub: vi.fn(), createClub: vi.fn(), deleteClub: vi.fn(), leaveClub: vi.fn(),
  addClubPost: vi.fn(), deleteClubPost: vi.fn(), addClubPoll: vi.fn(), deleteClubPoll: vi.fn(),
  voteClubPoll: vi.fn(), addClubEvent: vi.fn(), deleteClubEvent: vi.fn(), makeClubLink: vi.fn(),
  cancelClubLink: vi.fn(), deleteClubMember: vi.fn(), clubInviteLink: (t: string) => `https://x/invite#club:${t}`,
}));
vi.mock("./api", () => api);

import ClubsSection from "./ClubsSection";
import { ClubDetail, ClubSummary } from "./api";

/** Phase 3 item 10: clubs on the Fitness page. */

const summary: ClubSummary = {
  club_id: "c1", name: "Chess Club", about: "Wednesdays", owner_name: "Sam", is_owner: false, member_count: 3,
};

function detail(over: Partial<ClubDetail> = {}): ClubDetail {
  return {
    ...summary,
    posts: [{ post_id: "p1", body: "Tournament Saturday", created_at: "2026-10-28T00:00:00" }],
    polls: [{ poll_id: "q1", question: "Meet when?", options: ["Mon", "Wed"], closes_on: null, counts: [1, 2],
              my_vote: null, open: true }],
    events: [{ event_id: "e1", title: "Social", on_date: "2026-11-02", start_time: "18:00:00", end_time: null,
               location: "SUB" }],
    members: null, link: null, ...over,
  };
}

async function openClub(club: ClubDetail) {
  api.fetchClubs.mockResolvedValue([{ ...summary, is_owner: club.is_owner }]);
  api.fetchClub.mockResolvedValue(club);
  render(<ClubsSection userId="u1" />);
  fireEvent.click(await screen.findByRole("button", { name: /Chess Club/ }));
  return screen.findByRole("region", { name: "Chess Club" });
}

beforeEach(() => {
  Object.values(api).forEach((fn) => { if (typeof fn === "function" && "mockReset" in fn) fn.mockReset(); });
});
afterEach(cleanup);

describe("ClubsSection", () => {
  it("makes a club and opens it", async () => {
    api.fetchClubs.mockResolvedValueOnce([]).mockResolvedValue([{ ...summary, is_owner: true }]);
    api.createClub.mockResolvedValue({ ...detail(), is_owner: true });
    api.fetchClub.mockResolvedValue(detail({ is_owner: true }));
    render(<ClubsSection userId="u1" />);
    fireEvent.change(await screen.findByLabelText("New club name"), { target: { value: " Chess Club " } });
    fireEvent.click(screen.getByRole("button", { name: "New club" }));
    await waitFor(() => expect(api.createClub).toHaveBeenCalledWith("u1", "Chess Club", null));
    expect(await screen.findByRole("region", { name: "Chess Club" })).toBeTruthy();
  });

  it("shows a member the posts, polls and events, and lets them vote, not post", async () => {
    const view = await openClub(detail());
    expect(within(view).getByText("Tournament Saturday")).toBeTruthy();
    expect(within(view).getByText(/Social/)).toBeTruthy();
    expect(within(view).queryByLabelText("Announcement")).toBeNull();
    api.voteClubPoll.mockResolvedValue(detail({
      polls: [{ ...detail().polls[0], counts: [1, 3], my_vote: 1 }] }));
    fireEvent.click(within(view).getByRole("button", { name: "Wed · 2" }));
    await waitFor(() => expect(api.voteClubPoll).toHaveBeenCalledWith("u1", "c1", "q1", 1));
    expect((await within(view).findByRole("button", { name: "Wed · 3" })).getAttribute("aria-pressed")).toBe("true");
  });

  it("a closed poll can't be voted in", async () => {
    const view = await openClub(detail({ polls: [{ ...detail().polls[0], open: false }] }));
    expect((within(view).getByRole("button", { name: "Mon · 1" }) as HTMLButtonElement).disabled).toBe(true);
    expect(within(view).getByText(/closed/)).toBeTruthy();
  });

  it("lets the owner post and ask, splitting choices by line", async () => {
    const view = await openClub(detail({ is_owner: true, members: [], link: null }));
    api.addClubPoll.mockResolvedValue(detail({ is_owner: true }));
    fireEvent.change(within(view).getByLabelText("Question"), { target: { value: "Snacks?" } });
    fireEvent.change(within(view).getByLabelText("Choices, one per line"), { target: { value: "Yes\n\n No \n" } });
    fireEvent.click(within(view).getByRole("button", { name: "Ask" }));
    await waitFor(() => expect(api.addClubPoll).toHaveBeenCalledWith("u1", "c1", "Snacks?", ["Yes", "No"], null));
    api.addClubPost.mockResolvedValue(detail({ is_owner: true }));
    fireEvent.change(within(view).getByLabelText("Announcement"), { target: { value: " Bring boards " } });
    fireEvent.click(within(view).getByRole("button", { name: "Post" }));
    await waitFor(() => expect(api.addClubPost).toHaveBeenCalledWith("u1", "c1", "Bring boards"));
  });

  it("deletes an announcement only after asking", async () => {
    const view = await openClub(detail({ is_owner: true, members: [], link: null }));
    api.deleteClubPost.mockResolvedValue({ deleted: true });
    fireEvent.click(within(view).getByRole("button", { name: "Delete announcement" }));
    expect(api.deleteClubPost).not.toHaveBeenCalled();
    fireEvent.click(within(view).getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(api.deleteClubPost).toHaveBeenCalledWith("u1", "c1", "p1"));
  });

  it("a member leaves only after asking", async () => {
    const view = await openClub(detail());
    api.leaveClub.mockResolvedValue({ left: true });
    fireEvent.click(within(view).getByRole("button", { name: "Leave this club" }));
    expect(api.leaveClub).not.toHaveBeenCalled();
    fireEvent.click(within(view).getByRole("button", { name: "Leave" }));
    await waitFor(() => expect(api.leaveClub).toHaveBeenCalledWith("u1", "c1"));
  });
});

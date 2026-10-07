// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const api = {
  fetchPartners: vi.fn(), createInvite: vi.fn(), revokeInvite: vi.fn(), previewInvite: vi.fn(),
  acceptInvite: vi.fn(), endPartnership: vi.fn(),
};
vi.mock("./api", async () => {
  const real = await vi.importActual<typeof import("./api")>("./api");
  return {
    inviteLink: real.inviteLink,
    fetchPartners: (...a: unknown[]) => api.fetchPartners(...a),
    createInvite: (...a: unknown[]) => api.createInvite(...a),
    revokeInvite: (...a: unknown[]) => api.revokeInvite(...a),
    previewInvite: (...a: unknown[]) => api.previewInvite(...a),
    acceptInvite: (...a: unknown[]) => api.acceptInvite(...a),
    endPartnership: (...a: unknown[]) => api.endPartnership(...a),
  };
});
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import PartnersPanel, { figureWords } from "./PartnersPanel";
import InvitePage from "../../pages/InvitePage";
import { inviteLink } from "./api";
import { afterSignIn } from "../../pages/LoginPage";

/** Phase 2 item 10: accountability partners and invite links. */

const data = {
  mine: { week_percent: 75, streak_weeks: 2, figure_on: "2026-10-07" },
  partners: [{ partner_id: "p1", name: "Alex", since: "2026-10-01T00:00:00",
               figure: { week_percent: 100, streak_weeks: 1, figure_on: "2026-10-06" } }],
  invites: [{ id: "i1", created_at: "2026-10-05T00:00:00", expires_at: "2026-10-12T00:00:00" }],
};

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("figures, in words", () => {
  it("says the share done and the run of good weeks", () => {
    expect(figureWords({ week_percent: 75, streak_weeks: 2, figure_on: null }))
      .toBe("75% of this week's tasks done · 2 good weeks in a row");
    expect(figureWords({ week_percent: null, streak_weeks: 0, figure_on: null })).toBe("nothing due this week");
  });
});

describe("PartnersPanel", () => {
  it("shows your figure, each partner's, and your open links", async () => {
    api.fetchPartners.mockResolvedValue(data);
    render(<PartnersPanel userId="u1" />);
    expect(await screen.findByText(/What partners see of you: 75%/)).toBeTruthy();
    expect(screen.getByText("Alex")).toBeTruthy();
    expect(screen.getByText(/100% of this week's tasks done · 1 good week in a row/)).toBeTruthy();
    expect(screen.getByText(/A link you sent, open until/)).toBeTruthy();
  });

  it("asks before ending a partnership", async () => {
    api.fetchPartners.mockResolvedValue(data);
    api.endPartnership.mockResolvedValue({ ended: true });
    render(<PartnersPanel userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "End" }));
    expect(api.endPartnership).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    fireEvent.click(screen.getByRole("button", { name: "End" }));
    fireEvent.click(screen.getByRole("button", { name: "End partnership" }));
    await waitFor(() => expect(api.endPartnership).toHaveBeenCalledWith("u1", "p1"));
  });

  it("makes a link with the token in the fragment", async () => {
    api.fetchPartners.mockResolvedValue({ ...data, invites: [] });
    api.createInvite.mockResolvedValue({ id: "i2", token: "tok_abcdefghijklmnopqrstuv", expires_at: "2026-10-14T00:00:00" });
    render(<PartnersPanel userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Invite a partner" }));
    const field = await screen.findByLabelText("Invite link") as HTMLInputElement;
    expect(field.value).toMatch(/\/invite#tok_abcdefghijklmnopqrstuv$/);
  });

  it("says nothing when the read fails", async () => {
    api.fetchPartners.mockRejectedValue(new Error("down"));
    const { container } = render(<PartnersPanel userId="u1" />);
    await waitFor(() => expect(api.fetchPartners).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("the invite link", () => {
  it("keeps the token out of the path", () => {
    expect(inviteLink("abc", "https://account-2a7.pages.dev")).toBe("https://account-2a7.pages.dev/invite#abc");
  });
});

function openInvite(hash: string) {
  return render(
    <MemoryRouter initialEntries={[`/invite${hash}`]}>
      <Routes>
        <Route path="/invite" element={<InvitePage />} />
        <Route path="/tasks" element={<p>tasks page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InvitePage", () => {
  const token = "#tok_abcdefghijklmnopqrstuv";

  it("names who sent it and asks before anything happens", async () => {
    api.previewInvite.mockResolvedValue({ inviter_name: "Sam", kind: "partner" });
    api.acceptInvite.mockResolvedValue({ status: "accepted" });
    openInvite(token);
    expect(await screen.findByText("Sam")).toBeTruthy();
    expect(api.previewInvite).toHaveBeenCalledWith("u1", "tok_abcdefghijklmnopqrstuv");
    expect(api.acceptInvite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Become partners" }));
    expect(await screen.findByText("tasks page")).toBeTruthy();
  });

  it("says plainly when the link is dead", async () => {
    api.previewInvite.mockRejectedValue(new Error("404"));
    openInvite(token);
    expect(await screen.findByText(/expired, been used, or been cancelled/)).toBeTruthy();
  });

  it("explains your own link", async () => {
    api.previewInvite.mockResolvedValue({ inviter_name: "You", kind: "partner" });
    api.acceptInvite.mockResolvedValue({ status: "own" });
    openInvite(token);
    fireEvent.click(await screen.findByRole("button", { name: "Become partners" }));
    expect(await screen.findByText(/your own invite link/)).toBeTruthy();
  });
});

describe("after signing in", () => {
  it("goes back to the page that asked, and only to a page on this site", () => {
    expect(afterSignIn("/invite#tok")).toBe("/invite#tok");
    expect(afterSignIn("/tasks")).toBe("/tasks");
    for (const bad of ["//evil.example", "https://evil.example", "/\\evil", "", null, 7, "/login"]) {
      expect(afterSignIn(bad)).toBe("/");
    }
  });
});

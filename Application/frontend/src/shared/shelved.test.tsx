// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, renderHook, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { FITNESS_SHELVED, SHELVED_INVITE } from "./shelved";

/**
 * The closed shelf, as the app ships it: no way into the Fitness page, its
 * invite links refused without asking the API, and no club events fetched.
 * FitnessPage.test.tsx opens the shelf to keep the shelved page itself tested.
 */

const calls = vi.hoisted(() => ({
  previewTeamInvite: vi.fn(), previewClubInvite: vi.fn(), fetchClubEvents: vi.fn(),
}));
vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("../features/teams/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/teams/api")>()),
  previewTeamInvite: (...a: unknown[]) => calls.previewTeamInvite(...a),
}));
vi.mock("../features/clubs/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/clubs/api")>()),
  previewClubInvite: (...a: unknown[]) => calls.previewClubInvite(...a),
  fetchClubEvents: (...a: unknown[]) => calls.fetchClubEvents(...a),
}));
vi.mock("../features/calender/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/calender/api")>()),
  fetchAgenda: () => Promise.resolve([]),
}));
vi.mock("../features/tasks/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/tasks/api")>()),
  fetchTasks: () => Promise.resolve([]),
}));
vi.mock("../features/tasks/sharing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/tasks/sharing")>()),
  fetchSharedTasks: () => Promise.resolve([]),
}));
vi.mock("../features/calender/sharing", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/calender/sharing")>()),
  fetchSharedEvents: () => Promise.resolve([]),
}));
vi.mock("../features/jobs/applications/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../features/jobs/applications/api")>()),
  fetchApplications: () => Promise.resolve([]),
}));

import InvitePage from "../pages/InvitePage";
import { useCalender } from "../features/calender/hooks/useCalender";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function openInvite(fragment: string) {
  render(
    <MemoryRouter initialEntries={[`/invite#${fragment}`]}>
      <Routes><Route path="/invite" element={<InvitePage />} /></Routes>
    </MemoryRouter>,
  );
}

describe("the fitness shelf", () => {
  it("ships closed", () => {
    expect(FITNESS_SHELVED).toBe(true);
  });

  it("refuses a team link without asking the API", async () => {
    openInvite("team:tok_abcdefghijklmnopqrstuv");
    expect(await screen.findByText(SHELVED_INVITE)).toBeTruthy();
    expect(calls.previewTeamInvite).not.toHaveBeenCalled();
    expect(screen.queryByRole("button", { name: "Join the team" })).toBeNull();
  });

  it("refuses a club link without asking the API", async () => {
    openInvite("club:tok_abcdefghijklmnopqrstuv");
    expect(await screen.findByText(SHELVED_INVITE)).toBeTruthy();
    expect(calls.previewClubInvite).not.toHaveBeenCalled();
  });

  it("leaves the calendar without club events, and never asks for them", async () => {
    const { result } = renderHook(() => useCalender());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(calls.fetchClubEvents).not.toHaveBeenCalled();
  });
});

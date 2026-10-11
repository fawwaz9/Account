// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const api = vi.hoisted(() => ({
  fetchEventSharing: vi.fn(), makeEventLink: vi.fn(), cancelEventLink: vi.fn(), removeEventMember: vi.fn(),
  fetchSharedEvents: vi.fn(), leaveSharedEvent: vi.fn(), previewEventInvite: vi.fn(), acceptEventInvite: vi.fn(),
}));
vi.mock("../sharing", async () => {
  const real = await vi.importActual<typeof import("../sharing")>("../sharing");
  const mocked: Record<string, unknown> = {};
  for (const name of Object.keys(api) as (keyof typeof api)[]) {
    mocked[name] = (...a: unknown[]) => api[name](...a);
  }
  return { ...real, ...mocked };
});
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import EventSharingSection from "./EventSharingSection";
import SharedOccurrenceCard from "./SharedOccurrenceCard";
import InvitePage from "../../../pages/InvitePage";
import { eventInviteLink } from "../sharing";
import { sharedEventOccurrence, sharedTaskOccurrence } from "../hooks/useCalender";

/** Phase 2 item 9b (D24): shared events, and shared items on the calendar. */

const sharedEvent = {
  event_id: "e1", owner_name: "Sam", title: "Study group", kind: "personal", location: "Library 2F",
  notes: "bring the problem set", starts_on: "2026-10-22", start_time: "14:00:00", end_time: "15:30:00",
  member_names: ["Alex", "Kim"],
};

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("Sharing your own event", () => {
  const sharing = { members: [], link: null, shareable: true, max_members: 8 };

  it("makes a link with the token in the fragment, marked as an event's", async () => {
    api.fetchEventSharing.mockResolvedValue(sharing);
    api.makeEventLink.mockResolvedValue({ token: "tok_abcdefghijklmnopqrstuv", expires_at: "2026-10-17T00:00:00" });
    render(<EventSharingSection eventId="e1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Share with a link" }));
    const field = await screen.findByLabelText("Event link") as HTMLInputElement;
    expect(field.value).toMatch(/\/invite#event:tok_abcdefghijklmnopqrstuv$/);
    expect(api.makeEventLink).toHaveBeenCalledWith("u1", "e1");
  });

  it("says a repeat, a shift or a grade's block can't be shared", async () => {
    api.fetchEventSharing.mockResolvedValue({ ...sharing, shareable: false });
    render(<EventSharingSection eventId="e1" />);
    expect(await screen.findByText(/Only a one-off event can be shared/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Share with a link" })).toBeNull();
  });

  it("asks before taking someone off", async () => {
    api.fetchEventSharing.mockResolvedValue({ ...sharing, members: [{ id: "m1", name: "Alex", joined_at: "2026-10-10T00:00:00" }] });
    api.removeEventMember.mockResolvedValue({ removed: true });
    render(<EventSharingSection eventId="e1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Take off" }));
    expect(api.removeEventMember).not.toHaveBeenCalled();
    fireEvent.click(screen.getAllByRole("button", { name: "Take off" }).at(-1)!);
    await waitFor(() => expect(api.removeEventMember).toHaveBeenCalledWith("u1", "e1", "m1"));
  });
});

describe("shared items on your calendar", () => {
  it("turns someone's event into an occurrence marked as theirs", () => {
    const occurrence = sharedEventOccurrence(sharedEvent);
    expect(occurrence).toMatchObject({
      event_id: "e1", on_date: "2026-10-22", start_time: "14:00:00", course_id: null, repeats: false,
      shared: { owner_name: "Sam", member_names: ["Alex", "Kim"], what: "event" },
    });
  });

  it("puts someone's task on its due day, as a deadline off the clock", () => {
    const occurrence = sharedTaskOccurrence({
      task_id: "t1", owner_name: "Sam", title: "Group report", notes: null, due_date: "2026-10-20",
      due_time: "17:00:00", done: true, completed_at: null, member_names: ["Alex"],
    });
    expect(occurrence).toMatchObject({
      event_id: "t1", on_date: "2026-10-20", kind: "deadline", start_time: null, title: "✓ Group report",
      shared: { what: "task" },
    });
  });

  it("says whose an event is, offers no edit, and asks before you leave", async () => {
    api.leaveSharedEvent.mockResolvedValue({ left: true });
    const left = vi.fn();
    render(
      <MemoryRouter>
        <SharedOccurrenceCard userId="u1" occurrence={sharedEventOccurrence(sharedEvent)} onClose={vi.fn()} onLeft={left} />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Sam.s event · with Alex, Kim/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Edit|Delete/ })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Leave this event" }));
    expect(api.leaveSharedEvent).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Leave" }));
    await waitFor(() => expect(api.leaveSharedEvent).toHaveBeenCalledWith("u1", "e1"));
    await waitFor(() => expect(left).toHaveBeenCalled());
  });

  it("sends a shared task to the Tasks page rather than offering to leave it here", () => {
    render(
      <MemoryRouter>
        <SharedOccurrenceCard userId="u1" onClose={vi.fn()} onLeft={vi.fn()} occurrence={sharedTaskOccurrence({
          task_id: "t1", owner_name: "Sam", title: "Group report", notes: null, due_date: "2026-10-20",
          due_time: null, done: false, completed_at: null, member_names: ["Alex"],
        })} />
      </MemoryRouter>,
    );
    expect(screen.getByRole("link", { name: "Tasks page" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Leave this event" })).toBeNull();
  });
});

describe("an event link", () => {
  it("keeps the token out of the path", () => {
    expect(eventInviteLink("abc", "https://account-2a7.pages.dev")).toBe("https://account-2a7.pages.dev/invite#event:abc");
  });
});

function openInvite(hash: string) {
  return render(
    <MemoryRouter initialEntries={[`/invite${hash}`]}>
      <Routes>
        <Route path="/invite" element={<InvitePage />} />
        <Route path="/calendar" element={<p>calendar page</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("InvitePage, for an event", () => {
  const hash = "#event:tok_abcdefghijklmnopqrstuv";

  it("names the owner, the event and the day, and asks before adding it", async () => {
    api.previewEventInvite.mockResolvedValue({ owner_name: "Sam", title: "Study group", starts_on: "2026-10-22" });
    api.acceptEventInvite.mockResolvedValue({ status: "accepted" });
    openInvite(hash);
    expect(await screen.findByText("Study group")).toBeTruthy();
    expect(api.previewEventInvite).toHaveBeenCalledWith("u1", "tok_abcdefghijklmnopqrstuv");
    expect(api.acceptEventInvite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Add it to my calendar" }));
    expect(await screen.findByText("calendar page")).toBeTruthy();
  });

  it("explains your own link", async () => {
    api.previewEventInvite.mockResolvedValue({ owner_name: "You", title: "Study group", starts_on: "2026-10-22" });
    api.acceptEventInvite.mockResolvedValue({ status: "own" });
    openInvite(hash);
    fireEvent.click(await screen.findByRole("button", { name: "Add it to my calendar" }));
    expect(await screen.findByText(/your own event/)).toBeTruthy();
  });
});

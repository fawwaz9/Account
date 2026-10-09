// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

const api = vi.hoisted(() => ({
  fetchTaskSharing: vi.fn(), makeTaskLink: vi.fn(), cancelTaskLink: vi.fn(), removeTaskMember: vi.fn(),
  fetchSharedTasks: vi.fn(), updateSharedTask: vi.fn(), leaveSharedTask: vi.fn(),
  previewTaskInvite: vi.fn(), acceptTaskInvite: vi.fn(),
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

import SharedTasks from "./SharedTasks";
import TaskSharingSection from "./TaskSharingSection";
import InvitePage from "../../../pages/InvitePage";
import { taskInviteLink } from "../sharing";

/** Phase 2 item 9a (D23): shared tasks, from both sides, and the task link. */

const shared = {
  task_id: "t1", owner_name: "Sam", title: "Group report", notes: "draft by Friday",
  due_date: "2026-10-20", due_time: null, done: false, completed_at: null, member_names: ["Alex", "Kim"],
};

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("Shared with you", () => {
  it("shows nothing when you are on nobody's task", async () => {
    api.fetchSharedTasks.mockResolvedValue([]);
    const { container } = render(<SharedTasks userId="u1" />);
    await waitFor(() => expect(api.fetchSharedTasks).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("says whose task it is and who else is on it", async () => {
    api.fetchSharedTasks.mockResolvedValue([shared]);
    render(<SharedTasks userId="u1" />);
    expect(await screen.findByText("Group report")).toBeTruthy();
    expect(screen.getByText(/Sam.s · with Alex, Kim/)).toBeTruthy();
    expect(screen.getByText("draft by Friday")).toBeTruthy();
  });

  it("ticks it for everyone", async () => {
    api.fetchSharedTasks.mockResolvedValue([shared]);
    api.updateSharedTask.mockResolvedValue({ ...shared, done: true });
    render(<SharedTasks userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Complete Group report" }));
    await waitFor(() => expect(api.updateSharedTask).toHaveBeenCalledWith("u1", "t1", { done: true }));
  });

  it("edits only the title and notes", async () => {
    api.fetchSharedTasks.mockResolvedValue([shared]);
    api.updateSharedTask.mockResolvedValue(shared);
    render(<SharedTasks userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Group report" }));
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Final report " } });
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateSharedTask).toHaveBeenCalledWith(
      "u1", "t1", { title: "Final report", notes: null }));
  });

  it("asks before you leave", async () => {
    api.fetchSharedTasks.mockResolvedValue([shared]);
    api.leaveSharedTask.mockResolvedValue({ left: true });
    render(<SharedTasks userId="u1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Leave Group report" }));
    expect(api.leaveSharedTask).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Stay" }));
    fireEvent.click(screen.getByRole("button", { name: "Leave Group report" }));
    fireEvent.click(screen.getByRole("button", { name: "Leave" }));
    await waitFor(() => expect(api.leaveSharedTask).toHaveBeenCalledWith("u1", "t1"));
  });
});

describe("Sharing your own task", () => {
  const sharing = {
    members: [{ id: "m1", name: "Alex", joined_at: "2026-10-09T00:00:00" }],
    link: null, shareable: true, max_members: 8,
  };

  it("lists who is on it and asks before taking someone off", async () => {
    api.fetchTaskSharing.mockResolvedValue(sharing);
    api.removeTaskMember.mockResolvedValue({ removed: true });
    const changed = vi.fn();
    render(<TaskSharingSection taskId="t1" onChanged={changed} />);
    expect(await screen.findByText("Alex")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Take off" }));
    expect(api.removeTaskMember).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    fireEvent.click(screen.getByRole("button", { name: "Take off" }));
    expect(screen.getByText(/They lose it at once/)).toBeTruthy();
    fireEvent.click(screen.getAllByRole("button", { name: "Take off" }).at(-1)!);
    await waitFor(() => expect(api.removeTaskMember).toHaveBeenCalledWith("u1", "t1", "m1"));
    await waitFor(() => expect(changed).toHaveBeenCalled());
  });

  it("makes a link with the token in the fragment, marked as a task's", async () => {
    api.fetchTaskSharing.mockResolvedValue({ ...sharing, members: [] });
    api.makeTaskLink.mockResolvedValue({ token: "tok_abcdefghijklmnopqrstuv", expires_at: "2026-10-16T00:00:00" });
    render(<TaskSharingSection taskId="t1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Share with a link" }));
    const field = await screen.findByLabelText("Task link") as HTMLInputElement;
    expect(field.value).toMatch(/\/invite#task:tok_abcdefghijklmnopqrstuv$/);
    expect(screen.getByRole("button", { name: "Make a new link" })).toBeTruthy();
  });

  it("says a repeat can't be shared, and offers no link", async () => {
    api.fetchTaskSharing.mockResolvedValue({ ...sharing, members: [], shareable: false });
    render(<TaskSharingSection taskId="t1" />);
    expect(await screen.findByText(/can.t be shared/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Share with a link" })).toBeNull();
  });

  it("says nothing when the read fails", async () => {
    api.fetchTaskSharing.mockRejectedValue(new Error("down"));
    const { container } = render(<TaskSharingSection taskId="t1" />);
    await waitFor(() => expect(api.fetchTaskSharing).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

describe("a task link", () => {
  it("keeps the token out of the path", () => {
    expect(taskInviteLink("abc", "https://account-2a7.pages.dev")).toBe("https://account-2a7.pages.dev/invite#task:abc");
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

describe("InvitePage, for a task", () => {
  const hash = "#task:tok_abcdefghijklmnopqrstuv";

  it("names the owner and the task, and asks before joining", async () => {
    api.previewTaskInvite.mockResolvedValue({ owner_name: "Sam", title: "Group report" });
    api.acceptTaskInvite.mockResolvedValue({ status: "accepted" });
    openInvite(hash);
    expect(await screen.findByText("Group report")).toBeTruthy();
    expect(api.previewTaskInvite).toHaveBeenCalledWith("u1", "tok_abcdefghijklmnopqrstuv");
    expect(api.acceptTaskInvite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Join the task" }));
    expect(await screen.findByText("tasks page")).toBeTruthy();
    expect(api.acceptTaskInvite).toHaveBeenCalledWith("u1", "tok_abcdefghijklmnopqrstuv");
  });

  it("says when the task is full", async () => {
    api.previewTaskInvite.mockResolvedValue({ owner_name: "Sam", title: "Group report" });
    api.acceptTaskInvite.mockResolvedValue({ status: "full" });
    openInvite(hash);
    fireEvent.click(await screen.findByRole("button", { name: "Join the task" }));
    expect(await screen.findByText(/as many people on it as it can hold/)).toBeTruthy();
  });

  it("says plainly when the link is dead", async () => {
    api.previewTaskInvite.mockRejectedValue(new Error("404"));
    openInvite(hash);
    expect(await screen.findByText(/expired or been cancelled/)).toBeTruthy();
  });
});

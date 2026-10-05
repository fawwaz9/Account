// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchPendingQuestion: vi.fn(), answerQuestion: vi.fn() };
vi.mock("./api", () => ({
  fetchPendingQuestion: (...a: unknown[]) => api.fetchPendingQuestion(...a),
  answerQuestion: (...a: unknown[]) => api.answerQuestion(...a),
}));

import DisappointmentQuestion from "./DisappointmentQuestion";

async function show(question: "disappointment" | null = "disappointment") {
  api.fetchPendingQuestion.mockResolvedValue({ question });
  const view = render(<DisappointmentQuestion userId="u1" />);
  await waitFor(() => expect(api.fetchPendingQuestion).toHaveBeenCalledWith("u1"));
  return view;
}

beforeEach(() => {
  api.fetchPendingQuestion.mockReset();
  api.answerQuestion.mockReset();
});
afterEach(cleanup);

describe("DisappointmentQuestion", () => {
  it("asks when the server says to, and thanks you for an answer", async () => {
    api.answerQuestion.mockResolvedValue(null);
    await show();
    fireEvent.click(await screen.findByRole("button", { name: "Very disappointed" }));
    expect((await screen.findByRole("status")).textContent).toContain("Thanks");
    expect(api.answerQuestion).toHaveBeenCalledWith("u1", "very");
    expect(screen.queryByRole("button", { name: "Not disappointed" })).toBeNull();
  });

  it("takes 'don't ask again' as the answer it is", async () => {
    api.answerQuestion.mockResolvedValue(null);
    await show();
    fireEvent.click(await screen.findByRole("button", { name: "Don't ask again" }));
    expect((await screen.findByRole("status")).textContent).toContain("won't ask again");
    expect(api.answerQuestion).toHaveBeenCalledWith("u1", "dismissed");
  });

  it("acknowledges the press and holds the other buttons while saving", async () => {
    let finish: () => void = () => {};
    api.answerQuestion.mockReturnValue(new Promise<void>((resolve) => { finish = resolve; }));
    await show();
    fireEvent.click(await screen.findByRole("button", { name: "Somewhat disappointed" }));
    expect(screen.getByRole("button", { name: "Saving…" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "Not disappointed" }) as HTMLButtonElement).disabled).toBe(true);
    finish();
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("says so when saving fails, and keeps the question", async () => {
    api.answerQuestion.mockRejectedValue(new Error("500"));
    await show();
    fireEvent.click(await screen.findByRole("button", { name: "Not disappointed" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't save that");
    expect(screen.getByRole("button", { name: "Not disappointed" })).toBeTruthy();
  });

  it("shows nothing when there is nothing to ask, or the check fails", async () => {
    const quiet = await show(null);
    await Promise.resolve();
    expect(quiet.container.innerHTML).toBe("");
    quiet.unmount();

    api.fetchPendingQuestion.mockRejectedValue(new Error("404"));
    const failed = render(<DisappointmentQuestion userId="u1" />);
    await waitFor(() => expect(api.fetchPendingQuestion).toHaveBeenCalled());
    await Promise.resolve();
    expect(failed.container.innerHTML).toBe("");
  });
});

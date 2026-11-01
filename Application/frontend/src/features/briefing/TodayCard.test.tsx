// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = { fetchDigest: vi.fn() };
vi.mock("./api", () => ({ fetchDigest: (...a: unknown[]) => api.fetchDigest(...a) }));

import TodayCard from "./TodayCard";

/** Phase 4 item 6: the digest's own lines, so the card says what the briefing says. */

const TEXT = [
  "Monday, November 2.",
  "Today: CPSC 310 lecture 10am–11am (DMP 110).",
  "Overdue: 1 task — Reading 4.",
  "Exam: CPSC 310 midterm in 3 days — 2 open tasks, about 2h 30m.",
].join("\n");

beforeEach(() => { api.fetchDigest.mockReset(); });
afterEach(cleanup);

describe("TodayCard", () => {
  it("puts the date in the heading and every other line in the list", async () => {
    api.fetchDigest.mockResolvedValue({ text: TEXT });
    render(<TodayCard userId="u1" />);

    await waitFor(() => expect(screen.getByText("Monday, November 2")).toBeTruthy());
    expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(TEXT.split("\n").slice(1));
    expect(api.fetchDigest).toHaveBeenCalledWith("u1");
  });

  it("marks what needs attention", async () => {
    api.fetchDigest.mockResolvedValue({ text: TEXT });
    render(<TodayCard userId="u1" />);

    const overdue = await screen.findByText("Overdue: 1 task — Reading 4.");
    expect(overdue.className).toContain("todayLineWarn");
    expect(screen.getByText(/^Exam:/).className).toContain("todayLineExam");
  });

  it("renders nothing when the digest can't be read", async () => {
    api.fetchDigest.mockRejectedValue(new Error("down"));
    const { container } = render(<TodayCard userId="u1" />);

    await waitFor(() => expect(api.fetchDigest).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

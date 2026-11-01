// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchDropPreview: vi.fn() };
vi.mock("../api", () => ({ fetchDropPreview: (...a: unknown[]) => api.fetchDropPreview(...a) }));

import DropPreviewModal from "./DropPreviewModal";
import { DropPreview } from "../types";

/** Phase 4 item 11: before and after for a drop, the full-time check, never advice. */

function preview(fullTime: number): DropPreview {
  const below = 7 < fullTime;
  return {
    course_id: "c1", course_code: "CPSC 320", credits: 3,
    before: { semester_average: 76.5, cumulative_average: 88, cgpa: null, cumulative_average_including_term: 82.48,
      cgpa_including_term: null, term_credits: 10 },
    after: { semester_average: 72, cumulative_average: 88, cgpa: null, cumulative_average_including_term: 80,
      cgpa_including_term: null, term_credits: 7 },
    full_time_credits: fullTime, below_full_time: below, was_full_time: 10 >= fullTime, tuition_share: null,
    warnings: [
      ...(below ? [`This term would fall to 7 credits, under the ${fullTime} you set as full-time. Student loans...`] : []),
      "No tuition is recorded for this term, so no refund can be estimated.",
    ],
    disclaimers: ["Information, not advice."],
  };
}

beforeEach(() => {
  api.fetchDropPreview.mockReset();
  api.fetchDropPreview.mockImplementation((_u: string, _c: string, ft: number) => Promise.resolve(preview(ft)));
});
afterEach(cleanup);

function open() {
  render(<DropPreviewModal userId="u1" courseId="c1" courseCode="CPSC 320" onClose={() => {}} />);
}

describe("DropPreviewModal", () => {
  it("asks with the 9-credit default and shows now against without it", async () => {
    open();

    await screen.findByText("Credits this term");
    expect(api.fetchDropPreview).toHaveBeenCalledWith("u1", "c1", 9);
    const row = screen.getByText("Semester average").closest("tr")!;
    expect(within(row).getByText("76.5%")).toBeTruthy();
    expect(within(row).getByText("72%")).toBeTruthy();
  });

  it("leaves out rows with nothing on either side", async () => {
    open();

    await screen.findByText("Credits this term");
    expect(screen.queryByText("CGPA")).toBeNull();
  });

  it("puts the full-time warning first, marked serious", async () => {
    open();

    const note = await screen.findByRole("note");
    expect(note.textContent).toContain("under the 9 you set as full-time");
    expect(note.className).toContain("dropWarningSerious");
  });

  it("asks again when you change the full-time line", async () => {
    open();
    await screen.findByText("Credits this term");

    fireEvent.change(screen.getByRole("spinbutton", { name: "Credits a term that count as full-time" }),
      { target: { value: "6" } });

    await waitFor(() => expect(api.fetchDropPreview).toHaveBeenLastCalledWith("u1", "c1", 6));
    await waitFor(() => expect(screen.getByRole("note").className).not.toContain("dropWarningSerious"));
  });

  it("says it is information, not advice", async () => {
    open();

    expect(await screen.findByText("Information, not advice.")).toBeTruthy();
  });
});

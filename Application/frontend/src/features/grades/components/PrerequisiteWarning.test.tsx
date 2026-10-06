// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const api = { previewPrerequisites: vi.fn() };
vi.mock("../api", () => ({ previewPrerequisites: (...a: unknown[]) => api.previewPrerequisites(...a) }));

import PrerequisiteWarning from "./PrerequisiteWarning";
import { PrerequisitePreview } from "../types";

/** Phase 2 item 7: the warning while adding a course, never a block. */

const catalogue = { id: "k1", campus: "UBCV", subject: "CPSC", number: "221", title: null, credits: null };

function previewWith(status: "met" | "on_track" | "not_met"): PrerequisitePreview {
  return {
    catalogue,
    kinds: [{
      kind: "prerequisite", yours: null, applies: "shared",
      shared: {
        source: "reviewed", rule: {}, text: "CPSC 210", note: null, session: "2026W", source_text: null,
        review: null, result: { status, text: "CPSC 210", detail: "", parts: [], group: null },
      },
    }],
  };
}

beforeEach(() => { api.previewPrerequisites.mockReset(); });
afterEach(cleanup);

describe("PrerequisiteWarning", () => {
  it("warns when a shared rule is unmet, and says it can still be added", async () => {
    api.previewPrerequisites.mockResolvedValue(previewWith("not_met"));
    render(<PrerequisiteWarning userId="u1" code="CPSC_V 221" year={3} semester="Fall" />);
    expect(await screen.findByText(/CPSC 221’s prerequisites: CPSC 210\. Not met, and exceptions/)).toBeTruthy();
    expect(screen.getByText("You can still add it.")).toBeTruthy();
    expect(api.previewPrerequisites).toHaveBeenCalledWith("u1", "CPSC_V 221", 3, "Fall");
  });

  it("says nothing when the rule is met", async () => {
    api.previewPrerequisites.mockResolvedValue(previewWith("met"));
    const { container } = render(<PrerequisiteWarning userId="u1" code="CPSC_V 221" year={3} semester="Fall" />);
    await waitFor(() => expect(api.previewPrerequisites).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("does not ask until the code could be one", async () => {
    render(<PrerequisiteWarning userId="u1" code="CPS" year={3} semester="Fall" />);
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(api.previewPrerequisites).not.toHaveBeenCalled();
  });
});

// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = {
  fetchPrerequisites: vi.fn(), saveOwnPrerequisite: vi.fn(), deleteOwnPrerequisite: vi.fn(),
  checkPrerequisiteText: vi.fn(),
};
vi.mock("../api", () => ({
  fetchPrerequisites: (...a: unknown[]) => api.fetchPrerequisites(...a),
  saveOwnPrerequisite: (...a: unknown[]) => api.saveOwnPrerequisite(...a),
  deleteOwnPrerequisite: (...a: unknown[]) => api.deleteOwnPrerequisite(...a),
  checkPrerequisiteText: (...a: unknown[]) => api.checkPrerequisiteText(...a),
}));

import PrerequisitesPanel from "./PrerequisitesPanel";
import { PrerequisiteSide, Prerequisites, RuleResult } from "../types";

/** Phase 2 items 4 and 7: prerequisites on the course page, advisory (D3). */

const leaf = (status: RuleResult["status"], text: string, detail = ""): RuleResult =>
  ({ status, text, detail, parts: [], group: null });

function side(over: Partial<PrerequisiteSide>): PrerequisiteSide {
  return {
    source: "reviewed", rule: {}, text: "CPSC 210", note: null, session: "2026W", source_text: null,
    review: null, result: leaf("met", "CPSC 210", "CPSC_V 210 done (82%)"), ...over,
  };
}

function data(prereq: Partial<Prerequisites["kinds"][number]>): Prerequisites {
  return {
    course_id: "c1", link: { how: "matched", course: null },
    kinds: [
      { kind: "prerequisite", yours: null, shared: null, applies: null, ...prereq },
      { kind: "corequisite", yours: null, shared: null, applies: null },
    ],
  };
}

const show = () => render(<PrerequisitesPanel userId="u1" courseId="c1" />);

beforeEach(() => Object.values(api).forEach((fn) => fn.mockReset()));
afterEach(cleanup);

describe("PrerequisitesPanel", () => {
  it("says not met as a warning, with exceptions, never a block", async () => {
    const unmet: RuleResult = {
      status: "not_met", text: "CPSC 210 and MATH 200", detail: "", group: "all",
      parts: [leaf("met", "CPSC 210", "done"), leaf("not_met", "MATH 200", "MATH 200 is not on your record")],
    };
    api.fetchPrerequisites.mockResolvedValue(data({ shared: side({ result: unmet }), applies: "shared" }));
    show();
    expect(await screen.findByText(/Not met, and exceptions are sometimes made/)).toBeTruthy();
    expect(screen.getByText(/All of:/)).toBeTruthy();
    expect(screen.getByText(/MATH 200 is not on your record/)).toBeTruthy();
    expect(screen.getByText(/Shared, reviewed/)).toBeTruthy();
    expect(document.querySelectorAll("button:disabled")).toHaveLength(0);
  });

  it("puts yours first and the shared version behind it", async () => {
    api.fetchPrerequisites.mockResolvedValue(data({
      yours: side({ source: "syllabus", text: "CPSC 213", review: "pending", source_text: "Prereq: CPSC 213.",
                    result: leaf("on_track", "CPSC 213", "CPSC_V 213 in progress") }),
      shared: side({}), applies: "yours",
    }));
    show();
    expect(await screen.findByText(/On track/)).toBeTruthy();
    expect(screen.getByText(/Your version, from your syllabus/)).toBeTruthy();
    expect(screen.getByText(/waiting for review/)).toBeTruthy();
    expect(screen.getByText("Prereq: CPSC 213.")).toBeTruthy();
    expect(screen.getByText(/The shared version: CPSC 210/)).toBeTruthy();
  });

  it("offers to add your own when there are none", async () => {
    api.fetchPrerequisites.mockResolvedValue(data({}));
    show();
    expect(await screen.findByText("None recorded.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add your prerequisites" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Add your co-requisites" })).toBeTruthy();
  });

  it("reads a typed rule back and saves it", async () => {
    api.fetchPrerequisites.mockResolvedValue(data({}));
    api.checkPrerequisiteText.mockResolvedValue({ rule: {}, text: "CPSC 210 and MATH 200" });
    api.saveOwnPrerequisite.mockResolvedValue(data({
      yours: side({ source: "typed", text: "CPSC 210 and MATH 200", review: "pending" }), applies: "yours",
    }));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add your prerequisites" }));
    const input = screen.getByLabelText("Your prerequisites");
    fireEvent.change(input, { target: { value: "cpsc 210, math 200" } });
    fireEvent.blur(input);
    expect(await screen.findByText("Reads as: CPSC 210 and MATH 200")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.saveOwnPrerequisite).toHaveBeenCalledWith(
      "u1", "c1", { kind: "prerequisite", text: "cpsc 210, math 200", note: null }));
    expect(await screen.findByText(/Your version/)).toBeTruthy();
  });

  it("shows why a rule could not be read, and keeps what was typed", async () => {
    api.fetchPrerequisites.mockResolvedValue(data({}));
    api.saveOwnPrerequisite.mockRejectedValue(new Error("Didn't expect 'permission' there"));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add your prerequisites" }));
    fireEvent.change(screen.getByLabelText("Your prerequisites"), { target: { value: "permission" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/permission/);
    expect((screen.getByLabelText("Your prerequisites") as HTMLInputElement).value).toBe("permission");
  });

  it("removes yours and falls back to the shared one", async () => {
    api.fetchPrerequisites.mockResolvedValue(data({ yours: side({ source: "typed" }), shared: side({}), applies: "yours" }));
    api.deleteOwnPrerequisite.mockResolvedValue(data({ shared: side({}), applies: "shared" }));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Remove yours" }));
    expect(api.deleteOwnPrerequisite).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Keep" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove yours" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(api.deleteOwnPrerequisite).toHaveBeenCalledWith("u1", "c1", "prerequisite"));
    expect(await screen.findByText(/Shared, reviewed/)).toBeTruthy();
  });

  it("renders nothing when the read fails", async () => {
    api.fetchPrerequisites.mockRejectedValue(new Error("down"));
    const { container } = show();
    await waitFor(() => expect(api.fetchPrerequisites).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

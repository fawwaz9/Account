// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const api = {
  fetchAudit: vi.fn(), createRequirement: vi.fn(), updateRequirement: vi.fn(), deleteRequirement: vi.fn(),
  createEquivalence: vi.fn(), updateEquivalence: vi.fn(), deleteEquivalence: vi.fn(),
};
vi.mock("../../features/degree/api", () => ({
  fetchAudit: (...a: unknown[]) => api.fetchAudit(...a),
  createRequirement: (...a: unknown[]) => api.createRequirement(...a),
  updateRequirement: (...a: unknown[]) => api.updateRequirement(...a),
  deleteRequirement: (...a: unknown[]) => api.deleteRequirement(...a),
  createEquivalence: (...a: unknown[]) => api.createEquivalence(...a),
  updateEquivalence: (...a: unknown[]) => api.updateEquivalence(...a),
  deleteEquivalence: (...a: unknown[]) => api.deleteEquivalence(...a),
}));
vi.mock("../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import DegreePage from "./DegreePage";

const audit = {
  requirements: [
    {
      requirement: { id: "r1", name: "Core", kind: "courses", items: ["CPSC 110", "CPSC 221"],
        credits_needed: null, shares: false, position: 0 },
      items: [
        { item: "CPSC 110", met_by: { label: "COSC 111 + COSC 121 as CPSC 110", credits: 6, status: "completed" } },
        { item: "CPSC 221", met_by: null },
      ],
      counted: [], credits_completed: 6, credits_in_progress: 0, credits_planned: 0, done: false,
    },
    {
      requirement: { id: "r2", name: "Upper CPSC", kind: "credits", items: ["CPSC 3xx"],
        credits_needed: 6, shares: false, position: 1 },
      items: [],
      counted: [{ label: "CPSC 310", credits: 3, status: "completed" }, { label: "CPSC 320", credits: 3, status: "in_progress" }],
      credits_completed: 3, credits_in_progress: 3, credits_planned: 0, done: false,
    },
  ],
  equivalences: [{ id: "e1", from_codes: ["COSC 111", "COSC 121"], counts_as: ["CPSC 110"], credits: null, note: null }],
  credits_completed: 42, credits_in_progress: 12, credit_target: 120,
  not_counted: [{ label: "MUSC 100", credits: 3, status: "completed" }],
  failed: ["MATH 200"],
};

function show() {
  render(<MemoryRouter><DegreePage /></MemoryRouter>);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.fetchAudit.mockResolvedValue(audit);
});
afterEach(cleanup);

describe("DegreePage", () => {
  it("shows each requirement with what met it, what's missing, and the totals", async () => {
    show();
    expect(await screen.findByText("Core")).toBeTruthy();
    expect(document.querySelector(".degreeTotals")!.textContent).toBe("42 of 120 credits done, 12 in progress");
    expect(screen.getByText("COSC 111 + COSC 121 as CPSC 110 · done")).toBeTruthy();
    expect(screen.getByText("missing")).toBeTruthy();
    expect(screen.getByText("3 of 6 credits, 3 in progress")).toBeTruthy();
    expect(screen.getByText("CPSC 320")).toBeTruthy();
    expect(screen.getByText("COSC 111 + COSC 121 count as CPSC 110")).toBeTruthy();
    expect(screen.getByText("MUSC 100")).toBeTruthy();
    expect(screen.getByText("MATH 200")).toBeTruthy();
  });

  it("adds a requirement from lines, and shows the server's refusal", async () => {
    api.createRequirement.mockRejectedValueOnce(new Error('"CPSC 11" is not a course code or pattern.'));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add requirement" }));
    fireEvent.change(screen.getByLabelText("Requirement name"), { target: { value: "Upper" } });
    fireEvent.change(screen.getByLabelText("Kind"), { target: { value: "credits" } });
    fireEvent.change(screen.getByLabelText("Courses or patterns"), { target: { value: "CPSC 3xx\n\nCPSC 11" } });
    const save = screen.getByRole("button", { name: "Save requirement" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);  // credits needed not given
    fireEvent.change(screen.getByLabelText("Credits needed"), { target: { value: "6" } });
    fireEvent.click(save);
    expect((await screen.findByRole("alert")).textContent).toContain("not a course code");
    expect(api.createRequirement).toHaveBeenCalledWith("u1", {
      name: "Upper", kind: "credits", items: ["CPSC 3xx", "CPSC 11"], shares: false, credits_needed: 6,
    });
  });

  it("adds a mapping from codes joined by + and commas, then reloads", async () => {
    api.createEquivalence.mockResolvedValue({});
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Add mapping" }));
    fireEvent.change(screen.getByLabelText("Courses you took"), { target: { value: "COSC 211" } });
    fireEvent.change(screen.getByLabelText("Count as"), { target: { value: "CPSC 121, CPSC 213" } });
    fireEvent.click(screen.getByRole("button", { name: "Save mapping" }));
    await waitFor(() => expect(api.createEquivalence).toHaveBeenCalledWith("u1", {
      from_codes: ["COSC 211"], counts_as: ["CPSC 121", "CPSC 213"], credits: null, note: null,
    }));
    await waitFor(() => expect(api.fetchAudit).toHaveBeenCalledTimes(2));
  });

  it("confirms before removing, and says what is not touched", async () => {
    api.deleteRequirement.mockResolvedValue({ deleted: true });
    show();
    await screen.findByText("Core");
    fireEvent.click(screen.getAllByRole("button", { name: "Remove" })[0]);
    expect(screen.getByText(/"Core" will be removed from your audit\. Your courses are not touched\./)).toBeTruthy();
    expect(api.deleteRequirement).not.toHaveBeenCalled();
    const dialog = screen.getByRole("dialog");
    fireEvent.click(Array.from(dialog.querySelectorAll("button")).find((b) => b.textContent === "Remove")!);
    await waitFor(() => expect(api.deleteRequirement).toHaveBeenCalledWith("u1", "r1"));
  });
});

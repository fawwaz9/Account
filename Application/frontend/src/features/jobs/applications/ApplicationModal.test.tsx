// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Application } from "./types";

/** One application: its details, its history, and what happened next (D2). */

const api = vi.hoisted(() => ({
  createApplication: vi.fn(), updateApplication: vi.fn(), deleteApplication: vi.fn(),
  addStep: vi.fn(), deleteStep: vi.fn(),
}));
vi.mock("./api", () => api);
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import ApplicationModal from "./ApplicationModal";

afterEach(() => { cleanup(); vi.clearAllMocks(); });

const EXISTING: Application = {
  id: "a1", company: "Shopify", role: "Backend intern", applied_on: "2026-09-01", source: null, link: null,
  location: null, notes: null, status: "interview", deadline: null, follow_up_on: null, offer_amount: null,
  offer_period: null, last_step_on: "2026-09-10", quiet: false, created_at: null, updated_at: null,
  steps: [
    { id: "s1", status: "applied", on_date: "2026-09-01", note: null },
    { id: "s2", status: "interview", on_date: "2026-09-10", note: "first round" },
  ],
};

function show(application: Application | null) {
  const onSaved = vi.fn();
  render(<ApplicationModal open application={application} onClose={() => {}} onSaved={onSaved} />);
  return onSaved;
}

describe("a new application", () => {
  it("is created with what was typed", async () => {
    api.createApplication.mockResolvedValue({});
    show(null);
    fireEvent.change(screen.getByLabelText("Company"), { target: { value: "Shopify" } });
    fireEvent.change(screen.getByLabelText("Role"), { target: { value: "Backend intern" } });
    fireEvent.click(screen.getByRole("button", { name: "Add application" }));
    await waitFor(() => expect(api.createApplication).toHaveBeenCalled());
    const [, body] = api.createApplication.mock.calls[0];
    expect(body.company).toBe("Shopify");
    expect(body.offer_amount).toBeNull();
  });

  it("has no history until it exists", () => {
    show(null);
    expect(screen.queryByRole("region", { name: "History" })).toBeNull();
  });
});

describe("an existing application", () => {
  it("lists its history, and only steps after the first can be removed", () => {
    show(EXISTING);
    expect(screen.getByText("first round")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Remove the Applied step/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Remove the Interview step on 2026-09-10" })).toBeTruthy();
  });

  it("adds what happened next as a step", async () => {
    api.addStep.mockResolvedValue({ ...EXISTING, status: "offer" });
    show(EXISTING);
    fireEvent.change(screen.getByLabelText("What happened"), { target: { value: "offer" } });
    fireEvent.change(screen.getByLabelText("On"), { target: { value: "2026-09-20" } });
    fireEvent.click(screen.getByRole("button", { name: "Add update" }));
    await waitFor(() => expect(api.addStep).toHaveBeenCalledWith("u1", "a1",
      { status: "offer", on_date: "2026-09-20", note: null }));
  });

  it("removes a step only after asking", async () => {
    api.deleteStep.mockResolvedValue(EXISTING);
    show(EXISTING);
    fireEvent.click(screen.getByRole("button", { name: "Remove the Interview step on 2026-09-10" }));
    expect(api.deleteStep).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Remove the step" }));
    await waitFor(() => expect(api.deleteStep).toHaveBeenCalledWith("u1", "a1", "s2"));
  });

  it("deletes only after asking", async () => {
    api.deleteApplication.mockResolvedValue({ deleted: true });
    show(EXISTING);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(api.deleteApplication).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Delete the application" }));
    await waitFor(() => expect(api.deleteApplication).toHaveBeenCalledWith("u1", "a1"));
  });

  it("asks for the offer's pay once there is an offer, private and with its period", async () => {
    api.updateApplication.mockResolvedValue({});
    show({ ...EXISTING, status: "offer" });
    fireEvent.change(screen.getByLabelText("Pay offered (only you see this)"), { target: { value: "32.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.updateApplication).toHaveBeenCalled());
    const [, , body] = api.updateApplication.mock.calls[0];
    expect([body.offer_amount, body.offer_period]).toEqual([32.5, "hourly"]);
  });

  it("does not ask for pay before there is an offer", () => {
    show(EXISTING);
    expect(screen.queryByLabelText("Pay offered (only you see this)")).toBeNull();
  });
});

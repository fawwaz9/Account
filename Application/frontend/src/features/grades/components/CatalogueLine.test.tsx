// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchCatalogueLink: vi.fn(), searchCatalogue: vi.fn(), setCatalogueLink: vi.fn() };
vi.mock("../api", () => ({
  fetchCatalogueLink: (...a: unknown[]) => api.fetchCatalogueLink(...a),
  searchCatalogue: (...a: unknown[]) => api.searchCatalogue(...a),
  setCatalogueLink: (...a: unknown[]) => api.setCatalogueLink(...a),
}));

import CatalogueLine from "./CatalogueLine";
import { CatalogueCourse } from "../types";

/** Phase 2 item 3: which shared catalogue course a course is (D11). */

const cpsc221: CatalogueCourse = {
  id: "k1", campus: "UBCV", subject: "CPSC", number: "221", title: "Basic Algorithms", credits: 4,
};
const cosc221: CatalogueCourse = { ...cpsc221, id: "k2", campus: "UBCO", subject: "COSC", title: null };

function show() {
  return render(<CatalogueLine userId="u1" courseId="c1" />);
}

beforeEach(() => {
  Object.values(api).forEach((fn) => fn.mockReset());
  api.searchCatalogue.mockResolvedValue([cpsc221, cosc221]);
});
afterEach(cleanup);

describe("CatalogueLine", () => {
  it("names the matched course and says how", async () => {
    api.fetchCatalogueLink.mockResolvedValue({ how: "matched", course: cpsc221 });
    show();
    expect(await screen.findByText(/CPSC 221 · Basic Algorithms · UBC Vancouver/)).toBeTruthy();
    expect(screen.getByText(/matched by code/)).toBeTruthy();
  });

  it("says when nothing is listed yet", async () => {
    api.fetchCatalogueLink.mockResolvedValue({ how: "not_found", course: null });
    show();
    expect(await screen.findByText("not listed yet")).toBeTruthy();
  });

  it("renders nothing when the read fails", async () => {
    api.fetchCatalogueLink.mockRejectedValue(new Error("down"));
    const { container } = show();
    await waitFor(() => expect(api.fetchCatalogueLink).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("picks another course from the search", async () => {
    api.fetchCatalogueLink.mockResolvedValue({ how: "matched", course: cpsc221 });
    api.setCatalogueLink.mockResolvedValue({ how: "chosen", course: cosc221 });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    fireEvent.click(await screen.findByRole("button", { name: /COSC 221 · UBC Okanagan/ }));
    await waitFor(() =>
      expect(api.setCatalogueLink).toHaveBeenCalledWith("u1", "c1", { mode: "chosen", catalogue_course_id: "k2" }));
    expect(await screen.findByText(/your choice/)).toBeTruthy();
  });

  it("can be set to none, and back to matching", async () => {
    api.fetchCatalogueLink.mockResolvedValue({ how: "matched", course: cpsc221 });
    api.setCatalogueLink.mockResolvedValueOnce({ how: "none_chosen", course: null });
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    expect(screen.queryByRole("button", { name: "Match by code" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "None of these" }));
    expect(await screen.findByText("none, by your choice")).toBeTruthy();

    api.setCatalogueLink.mockResolvedValueOnce({ how: "matched", course: cpsc221 });
    fireEvent.click(screen.getByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "Match by code" }));
    await waitFor(() => expect(api.setCatalogueLink).toHaveBeenLastCalledWith("u1", "c1", { mode: "auto" }));
  });

  it("keeps the link and says so when a save fails", async () => {
    api.fetchCatalogueLink.mockResolvedValue({ how: "matched", course: cpsc221 });
    api.setCatalogueLink.mockRejectedValue(new Error("nope"));
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Change" }));
    fireEvent.click(screen.getByRole("button", { name: "None of these" }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/as it was/);
    expect(screen.getByText(/matched by code/)).toBeTruthy();
  });
});

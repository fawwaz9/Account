// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchCourseSyllabi: vi.fn(), fetchSyllabusFile: vi.fn() };
vi.mock("./api", () => ({
  fetchCourseSyllabi: (...a: unknown[]) => api.fetchCourseSyllabi(...a),
  fetchSyllabusFile: (...a: unknown[]) => api.fetchSyllabusFile(...a),
}));

import KeptSyllabi from "./KeptSyllabi";

const kept = { id: "p1", filename: "cpsc221.pdf", media_type: "application/pdf", created_at: "2026-10-05T04:00:00" };

beforeEach(() => {
  api.fetchCourseSyllabi.mockReset();
  api.fetchSyllabusFile.mockReset();
  URL.createObjectURL = vi.fn(() => "blob:x");
  URL.revokeObjectURL = vi.fn();
});
afterEach(cleanup);

describe("KeptSyllabi", () => {
  it("renders nothing when no syllabus was kept", async () => {
    api.fetchCourseSyllabi.mockResolvedValue([]);
    const { container } = render(<KeptSyllabi userId="u1" courseId="c1" />);
    await waitFor(() => expect(api.fetchCourseSyllabi).toHaveBeenCalledWith("u1", "c1"));
    expect(container.innerHTML).toBe("");
  });

  it("downloads the kept file, saying so while it does", async () => {
    api.fetchCourseSyllabi.mockResolvedValue([kept]);
    let finish: (b: Blob) => void = () => {};
    api.fetchSyllabusFile.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(<KeptSyllabi userId="u1" courseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Syllabus · cpsc221.pdf" }));
    expect(screen.getByRole("button", { name: "Downloading…" })).toBeTruthy();
    finish(new Blob(["%PDF"]));
    await waitFor(() => expect(click).toHaveBeenCalledTimes(1));
    expect(api.fetchSyllabusFile).toHaveBeenCalledWith("u1", "p1");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:x");
    expect(await screen.findByRole("button", { name: "Syllabus · cpsc221.pdf" })).toBeTruthy();
    click.mockRestore();
  });

  it("says when the download failed", async () => {
    api.fetchCourseSyllabi.mockResolvedValue([kept]);
    api.fetchSyllabusFile.mockRejectedValue(new Error("502"));
    render(<KeptSyllabi userId="u1" courseId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Syllabus · cpsc221.pdf" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Couldn't download");
  });
});

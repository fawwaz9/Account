// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";

const api = { fetchSalaries: vi.fn() };
vi.mock("./api", () => ({ fetchSalaries: (...a: unknown[]) => api.fetchSalaries(...a) }));

import CoopPay from "./CoopPay";

/** Phase 3 item 12: shared co-op pay per employer, above the floor (D11, D12). */

beforeEach(() => { api.fetchSalaries.mockReset(); });
afterEach(cleanup);

describe("CoopPay", () => {
  it("lists each employer's median and middle half", async () => {
    api.fetchSalaries.mockResolvedValue([
      { employer: "Shopify", people: 10, median: 30, p25: 28.5, p75: 32 },
    ]);
    render(<CoopPay userId="u1" />);
    const section = await screen.findByRole("region", { name: "Co-op pay" });
    const row = within(section).getByRole("listitem");
    expect(row.textContent).toMatch(/Shopify/);
    expect(row.textContent).toMatch(/\$30\.00\/h/);
    expect(row.textContent).toMatch(/middle half \$28\.50–\$32\.00 · 10 offers/);
    expect(api.fetchSalaries).toHaveBeenCalledWith("u1");
  });

  it("says what it is waiting for while no employer has reached the floor", async () => {
    api.fetchSalaries.mockResolvedValue([]);
    render(<CoopPay userId="u1" />);
    expect(await screen.findByText(/once 5 students have shared verified offers/)).toBeTruthy();
  });

  it("renders nothing when the read fails", async () => {
    api.fetchSalaries.mockRejectedValue(new Error("down"));
    const { container } = render(<CoopPay userId="u1" />);
    await waitFor(() => expect(api.fetchSalaries).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });
});

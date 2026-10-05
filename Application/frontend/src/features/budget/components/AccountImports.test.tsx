// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { fetchImports: vi.fn(), deleteImport: vi.fn() };
vi.mock("../api", () => ({
  fetchImports: (...a: unknown[]) => api.fetchImports(...a),
  deleteImport: (...a: unknown[]) => api.deleteImport(...a),
}));

import AccountImports from "./AccountImports";

const mine = {
  id: "i1", account_id: "a1", account_name: "Chequing", filename: "oct.csv",
  created_at: "2026-10-05T03:00:00", row_count: 42, rows_remaining: 40,
  first_date: "2026-10-01", last_date: "2026-10-31", subscription_candidates: null,
};
const elsewhere = { ...mine, id: "i2", account_id: "a2", filename: "savings.csv" };

beforeEach(() => {
  api.fetchImports.mockReset();
  api.deleteImport.mockReset();
  api.fetchImports.mockResolvedValue([mine, elsewhere]);
});
afterEach(cleanup);

function show(onUndone = vi.fn()) {
  render(<AccountImports userId="u1" accountId="a1" nonce={0} onUndone={onUndone} />);
  return onUndone;
}

describe("AccountImports", () => {
  it("lists only this account's imports", async () => {
    show();
    expect(await screen.findByText(/oct\.csv/)).toBeTruthy();
    expect(screen.queryByText(/savings\.csv/)).toBeNull();
    expect(screen.getByText("40 of 42 rows still here")).toBeTruthy();
  });

  it("asks before undoing, says how much goes, and removes nothing on cancel", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(screen.getByText(/removes the 40 rows it added/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /cancel|keep/i }));
    expect(api.deleteImport).not.toHaveBeenCalled();
  });

  it("undoes on confirmation, and tells the page", async () => {
    api.deleteImport.mockResolvedValue({ removed: 40 });
    const onUndone = show();
    fireEvent.click(await screen.findByRole("button", { name: "Undo" }));
    api.fetchImports.mockResolvedValue([elsewhere]);
    fireEvent.click(screen.getByRole("button", { name: "Undo import" }));
    await waitFor(() => expect(api.deleteImport).toHaveBeenCalledWith("u1", "i1"));
    await waitFor(() => expect(onUndone).toHaveBeenCalled());
    await waitFor(() => expect(screen.queryByText(/oct\.csv/)).toBeNull());
  });

  it("says nothing when this account has no imports", async () => {
    api.fetchImports.mockResolvedValue([elsewhere]);
    const { container } = render(<AccountImports userId="u1" accountId="a1" nonce={0} onUndone={vi.fn()} />);
    await waitFor(() => expect(api.fetchImports).toHaveBeenCalled());
    expect(container.innerHTML).toBe("");
  });
});

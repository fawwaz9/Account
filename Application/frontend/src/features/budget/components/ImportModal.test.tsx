// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { previewImport: vi.fn(), commitImport: vi.fn() };
vi.mock("../api", () => ({
  previewImport: (...a: unknown[]) => api.previewImport(...a),
  commitImport: (...a: unknown[]) => api.commitImport(...a),
}));

import ImportModal from "./ImportModal";
import { ImportPreview } from "../types";

const CSV = "Date,Description,Amount\n2026-10-01,Coffee,-4.50\n2026-10-02,Pay,812.40\nsoon,Bad,-1\n";

const preview: ImportPreview = {
  account_id: "a1",
  mapping: { has_header: true, date: 0, description: [1], amount: 2, debit: null, credit: null,
    date_order: "mdy", invert: false },
  columns: ["Date", "Description", "Amount"],
  date_order_assumed: false,
  rows: [
    { line: 2, on_date: "2026-10-01", description: "Coffee", amount: -4.5, status: "duplicate",
      duplicate_of: "t1", reason: "Already in this account" },
    { line: 3, on_date: "2026-10-02", description: "Pay", amount: 812.4, status: "new",
      duplicate_of: null, reason: null },
    { line: 4, on_date: null, description: "Bad", amount: null, status: "error",
      duplicate_of: null, reason: "Couldn't read a date from \"soon\"" },
  ],
  new_count: 1, duplicate_count: 1, error_count: 1, money_in: 812.4, money_out: 0,
};

function show(onImported = vi.fn()) {
  render(<ImportModal userId="u1" accountId="a1" accountName="Chequing" onClose={vi.fn()} onImported={onImported} />);
  return onImported;
}

async function choose() {
  const file = new File([CSV], "oct.csv", { type: "text/csv" });
  fireEvent.change(screen.getByLabelText("CSV file"), { target: { files: [file] } });
  await screen.findByText(/1 new · 1 already in this account · 1 couldn't be read/);
}

const box = (line: number) => screen.getByLabelText(`Import line ${line}`) as HTMLInputElement;

beforeEach(() => {
  api.previewImport.mockReset();
  api.commitImport.mockReset();
  api.previewImport.mockResolvedValue(preview);
});
afterEach(cleanup);

describe("ImportModal", () => {
  it("reads the file and shows what it would add, writing nothing", async () => {
    show();
    await choose();
    expect(api.previewImport).toHaveBeenCalledWith("u1", "a1", CSV, null);
    expect(api.commitImport).not.toHaveBeenCalled();
  });

  it("ticks new rows, leaves duplicates unticked, and never offers an unreadable line", async () => {
    show();
    await choose();
    expect(box(3).checked).toBe(true);
    expect(box(2).checked).toBe(false);
    expect(box(4).disabled).toBe(true);
    expect(screen.getByText("Already in this account")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Import 1 row" })).toBeTruthy();
  });

  it("imports the ticked lines, a duplicate included only if ticked on purpose", async () => {
    api.commitImport.mockResolvedValue({ id: "i1", row_count: 2, subscription_candidates: 1 });
    const onImported = show();
    await choose();
    fireEvent.click(box(2));
    fireEvent.click(screen.getByRole("button", { name: "Import 2 rows" }));
    expect((await screen.findByRole("status")).textContent).toContain("2 rows added to Chequing");
    expect(api.commitImport).toHaveBeenCalledWith("u1", "a1", CSV, preview.mapping, [2, 3], "oct.csv");
    expect(onImported).toHaveBeenCalled();
    expect(screen.getByText(/1 repeating charge looks like a subscription/)).toBeTruthy();
  });

  it("re-reads the file when a column is changed", async () => {
    show();
    await choose();
    fireEvent.change(screen.getByLabelText("Date order"), { target: { value: "dmy" } });
    await waitFor(() => expect(api.previewImport).toHaveBeenCalledTimes(2));
    expect(api.previewImport).toHaveBeenLastCalledWith("u1", "a1", CSV, { ...preview.mapping, date_order: "dmy" });
  });

  it("acknowledges the import while it runs", async () => {
    let finish: (value: unknown) => void = () => {};
    api.commitImport.mockReturnValue(new Promise((resolve) => { finish = resolve; }));
    show();
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Import 1 row" }));
    expect((screen.getByRole("button", { name: "Importing…" }) as HTMLButtonElement).disabled).toBe(true);
    finish({ id: "i1", row_count: 1, subscription_candidates: 0 });
    expect(await screen.findByRole("status")).toBeTruthy();
  });

  it("shows why a file couldn't be read", async () => {
    api.previewImport.mockRejectedValue(new Error("The file has no rows"));
    show();
    fireEvent.change(screen.getByLabelText("CSV file"), {
      target: { files: [new File([""], "empty.csv", { type: "text/csv" })] },
    });
    expect((await screen.findByRole("alert")).textContent).toBe("The file has no rows");
  });

  it("warns when every date reads both ways", async () => {
    api.previewImport.mockResolvedValue({ ...preview, date_order_assumed: true });
    show();
    await choose();
    expect(screen.getByText(/Every date reads both ways/)).toBeTruthy();
  });
});

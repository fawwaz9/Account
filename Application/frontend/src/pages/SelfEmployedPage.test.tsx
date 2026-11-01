// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Client, Invoice, SelfEmployment } from "../features/jobs/types";

/** The self-employed page (Phase 4 item 15): invoices and their states, the CRA watch, tagging. */

const api = vi.hoisted(() => ({
  fetchSelfEmployment: vi.fn(), fetchInvoices: vi.fn(), fetchClients: vi.fn(), markInvoicePaid: vi.fn(),
  markInvoiceUnpaid: vi.fn(), createInvoice: vi.fn(), createClient: vi.fn(), updateInvoice: vi.fn(),
  deleteInvoice: vi.fn(), updateClient: vi.fn(), deleteClient: vi.fn(),
}));
const money = vi.hoisted(() => ({ fetchAccounts: vi.fn(), fetchTransactions: vi.fn(), updateTransaction: vi.fn() }));
vi.mock("../features/jobs/api", () => api);
vi.mock("../features/budget/api", () => money);
vi.mock("../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));
vi.mock("../shared/utils/dateUtils", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../shared/utils/dateUtils")>()),
  today: () => "2026-11-01",
}));

import SelfEmployedPage from "./SelfEmployedPage";

function invoice(over: Partial<Invoice>): Invoice {
  return {
    id: "i1", client_id: "c1", client: "Acme Tutoring", number: "INV-001", description: null,
    issued_on: "2026-10-01", due_on: "2026-10-31", amount: 120, paid_on: null, state: "outstanding",
    days_overdue: null, deposited: false, ...over,
  };
}

const CLIENTS: Client[] = [{ id: "c1", name: "Acme Tutoring", archived: false, invoices: 2, invoiced: 320, unpaid: 120 }];

function year(over: Partial<SelfEmployment> = {}): SelfEmployment {
  return {
    year: 2026, revenue: 15000, received: 9000, business_expenses: 500, net: 14500, unpaid: 120,
    overdue: [invoice({ id: "late", number: "INV-002", state: "overdue", days_overdue: 12, due_on: "2026-10-20" })],
    expenses: [{ transaction_id: "t1", occurred_on: "2026-10-03", description: "Phone", amount: 80, percent: 50,
                 business_amount: 40 }],
    cpp: { figures_year: 2026, rate: 11.9, exemption: 3500, ceiling: 74600, second_rate: 8, second_ceiling: 85000,
           employment_gross: 0, base: 1309, second: 0, total: 1309 },
    instalments: { threshold: 3000, dates: ["2026-03-15", "2026-06-15", "2026-09-15", "2026-12-15"], next_due: "2026-12-15" },
    gst: { threshold: 30000, four_quarter_total: 25000, level: "approaching", quarters: [
      { label: "Jan-Mar 2026", starts_on: "2026-01-01", total: 7000 },
      { label: "Apr-Jun 2026", starts_on: "2026-04-01", total: 6000 },
      { label: "Jul-Sep 2026", starts_on: "2026-07-01", total: 8000 },
      { label: "Oct-Dec 2026", starts_on: "2026-10-01", total: 4000 }] },
    typical_month: { low: 400, high: 900, months: 6 },
    next_number: "INV-003",
    sources: [{ label: "CRA: When to register for and start charging the GST/HST", url: "https://www.canada.ca/x.html" }],
    note: "Tax information from what you've recorded, not tax advice.",
    ...over,
  };
}

function show() {
  return render(<MemoryRouter initialEntries={["/jobs/self-employed"]}><SelfEmployedPage /></MemoryRouter>);
}

beforeEach(() => {
  api.fetchSelfEmployment.mockResolvedValue(year());
  api.fetchInvoices.mockResolvedValue([
    invoice({}), invoice({ id: "p1", number: "INV-000", state: "paid", paid_on: "2026-09-20", deposited: true }),
  ]);
  api.fetchClients.mockResolvedValue(CLIENTS);
  api.markInvoicePaid.mockResolvedValue({});
  api.createInvoice.mockResolvedValue({});
  money.fetchAccounts.mockResolvedValue([{ id: "a1", name: "Chequing", archived: false }]);
  money.fetchTransactions.mockResolvedValue([
    { id: "t9", kind: "expense", amount: 30, description: "Printer ink", occurred_on: "2026-10-28", business_percent: null },
    { id: "t8", kind: "income", amount: 300, description: "Pay", occurred_on: "2026-10-28", business_percent: null },
  ]);
  money.updateTransaction.mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe("the self-employed page", () => {
  it("leads with what's overdue, then the year's figures and a range, never one number", async () => {
    show();
    const overdue = await screen.findByRole("region", { name: "Overdue invoices" });
    expect(within(overdue).getByText(/INV-002 to Acme Tutoring/)).toBeTruthy();
    expect(within(overdue).getByText("12 days overdue")).toBeTruthy();
    expect(screen.getByText("Net self-employment")).toBeTruthy();
    expect(screen.getByText(/typically brings in \$400/)).toBeTruthy();
  });

  it("lists open invoices and keeps the paid ones behind a button", async () => {
    show();
    const list = await screen.findByRole("region", { name: "Invoices" });
    expect(within(list).getByText("INV-001 · Acme Tutoring")).toBeTruthy();
    expect(within(list).queryByText("INV-000 · Acme Tutoring")).toBeNull();
    fireEvent.click(within(list).getByText("Show 1 paid"));
    expect(within(list).getByText("INV-000 · Acme Tutoring")).toBeTruthy();
    expect(within(list).getByText("Paid Sun 20 Sep")).toBeTruthy();
  });

  it("marks an invoice paid into an account", async () => {
    show();
    const list = await screen.findByRole("region", { name: "Invoices" });
    fireEvent.click(within(list).getByText("Mark paid"));
    fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Mark paid" }));
    await waitFor(() => expect(api.markInvoicePaid).toHaveBeenCalledWith("u1", "i1",
      { paid_on: "2026-11-01", account_id: "a1" }));
  });

  it("can mark one paid without writing to the ledger", async () => {
    show();
    const list = await screen.findByRole("region", { name: "Invoices" });
    fireEvent.click(within(list).getByText("Mark paid"));
    fireEvent.change(await screen.findByLabelText("Record it in"), { target: { value: "__already__" } });
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Mark paid" }));
    await waitFor(() => expect(api.markInvoicePaid).toHaveBeenCalledWith("u1", "i1", { paid_on: "2026-11-01" }));
  });

  it("suggests the next number for a new invoice", async () => {
    show();
    await screen.findByRole("region", { name: "Invoices" });
    fireEvent.click(screen.getByRole("button", { name: "New invoice" }));
    expect((await screen.findByLabelText("Invoice number") as HTMLInputElement).value).toBe("INV-003");
    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "75" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await waitFor(() => expect(api.createInvoice).toHaveBeenCalledWith("u1", {
      client_id: "c1", number: "INV-003", amount: 75, issued_on: "2026-11-01", description: null }));
  });

  it("reads the CRA rules with their sources", async () => {
    show();
    const rules = await screen.findByRole("region", { name: "Tax rules" });
    expect(within(rules).getByText(/Approaching the line/)).toBeTruthy();
    expect(within(rules).getByText(/\$1,309\.00/)).toBeTruthy();
    expect(within(rules).getByText("Tue 15 Dec")).toBeTruthy();
    expect(within(rules).getByRole("link", { name: /When to register/ }).getAttribute("href"))
      .toBe("https://www.canada.ca/x.html");
    expect(within(rules).getByText(/doesn.t estimate your income tax/)).toBeTruthy();
  });

  it("tags a recent expense as half business, offering expenses only", async () => {
    show();
    const panel = await screen.findByRole("region", { name: "Business expenses" });
    await waitFor(() => expect(within(panel).getByText(/Printer ink/)).toBeTruthy());
    expect(within(panel).queryByText(/· Pay ·/)).toBeNull();
    fireEvent.change(within(panel).getByLabelText("Tag a recent expense"), { target: { value: "t9" } });
    fireEvent.change(within(panel).getByLabelText("Business share %"), { target: { value: "50" } });
    fireEvent.click(within(panel).getByRole("button", { name: "Tag" }));
    await waitFor(() => expect(money.updateTransaction).toHaveBeenCalledWith("u1", "t9", { business_percent: 50 }));
  });
});

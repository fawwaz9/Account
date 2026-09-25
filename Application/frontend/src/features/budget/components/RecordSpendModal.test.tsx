// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

/**
 * The account is the point of this dialog.
 *
 * Every other way of recording an expense asks which account it came from.
 * This one does not, because it is opened from that account's own page -- so
 * the thing actually worth pinning is that what it sends is the account on
 * screen, and that nothing in the form can change it.
 */

// Typed with its real signature, so `mock.calls[0]` is a pair rather than an
// empty tuple -- without it the payload assertions below need a cast that tsc
// rejects, and the suite would pass while `npm run build` failed.
const createTransaction = vi.fn(
  async (_userId: string, _payload: Record<string, unknown>) => ({}),
);
vi.mock("../api", () => ({ createTransaction }));
vi.mock("../../../app/auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "user-1" } }),
}));
// The picker resolves a course code through the server; irrelevant here, and
// stubbed so the dialog does not depend on a network call to render.
vi.mock("./CoursePicker", () => ({ default: () => null }));

const { default: RecordSpendModal } = await import("./RecordSpendModal");

const CATEGORIES = [
  { id: "cat-food", name: "Food", archived: false, position: 0 },
  { id: "cat-books", name: "Books", archived: false, position: 1 },
];

function show(over: Record<string, unknown> = {}) {
  return render(
    <RecordSpendModal
      open
      accountId="acct-chequing"
      accountName="Chequing"
      categories={CATEGORIES}
      courses={[]}
      onClose={vi.fn()}
      onSaved={vi.fn()}
      {...over}
    />,
  );
}

function fill(amount: string) {
  fireEvent.change(screen.getByLabelText("Amount"), { target: { value: amount } });
}

beforeEach(() => createTransaction.mockClear());
afterEach(cleanup);

describe("recording spending from an account", () => {
  it("names the account it will charge", () => {
    show();
    expect(screen.getByText(/Chequing/)).toBeDefined();
  });

  /** The whole reason this dialog exists rather than the four-mode one. */
  it("offers no way to pick a different account", () => {
    show();

    const selects = screen.queryAllByRole("combobox");
    // Category is a select and is allowed; an account picker is not.
    expect(selects).toHaveLength(1);
    expect(selects[0].id).toBe("spend-category");
  });

  it("sends the account from the page, as an expense", async () => {
    const onSaved = vi.fn();
    const onClose = vi.fn();
    show({ onSaved, onClose });

    fill("24.50");
    fireEvent.change(screen.getByLabelText("Description"), { target: { value: "Lunch" } });
    fireEvent.change(screen.getByLabelText("Category"), { target: { value: "cat-food" } });
    fireEvent.click(screen.getByRole("button", { name: "Record" }));

    await waitFor(() => expect(createTransaction).toHaveBeenCalledTimes(1));
    const [, payload] = createTransaction.mock.calls[0];
    expect(payload.account_id).toBe("acct-chequing");
    expect(payload.kind).toBe("expense");
    expect(payload.amount).toBe(24.5);
    expect(payload.category_id).toBe("cat-food");
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  /**
   * Uncategorised is a real answer, so the empty option must send null rather
   * than the empty string -- which the server would reject as a malformed uuid.
   */
  it("sends null for uncategorised, not an empty string", async () => {
    show();
    fill("9");
    fireEvent.click(screen.getByRole("button", { name: "Record" }));

    await waitFor(() => expect(createTransaction).toHaveBeenCalled());
    const [, payload] = createTransaction.mock.calls[0];
    expect(payload.category_id).toBeNull();
    expect(payload.description).toBeNull();
  });

  /**
   * A failed write keeps what was typed. Closing here would throw the entry
   * away at the one moment it could not be saved anywhere else.
   */
  it("stays open and shows why when the write fails", async () => {
    createTransaction.mockRejectedValueOnce(new Error("Account not found"));
    const onClose = vi.fn();
    const onSaved = vi.fn();
    show({ onClose, onSaved });

    fill("12");
    fireEvent.click(screen.getByRole("button", { name: "Record" }));

    await waitFor(() => expect(screen.getByText("Account not found")).toBeDefined());
    expect(onClose).not.toHaveBeenCalled();
    expect(onSaved).not.toHaveBeenCalled();
    expect((screen.getByLabelText("Amount") as HTMLInputElement).value).toBe("12");
  });

  it("renders nothing at all when closed", () => {
    show({ open: false });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

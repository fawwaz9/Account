// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";

const api = { setSubcategoryWeights: vi.fn() };
vi.mock("../api", () => ({ setSubcategoryWeights: (...a: unknown[]) => api.setSubcategoryWeights(...a) }));
vi.mock("../../../app/auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "u1" } }) }));

import SubcategoryWeightsModal from "./SubcategoryWeightsModal";
import GradeCategoryColumn from "./GradeCategoryColumn";
import { Grade, GradeCategory, GradeSchedule } from "../types";
import { addsUp, evenSplit } from "../subcategory";

/** D29: a category's weight split between its items, adding up to it, or shared evenly. */

function grade(id: string, name: string, score: number | null, max: number, share: number | null = null): Grade {
  return {
    id, name, score, max_score: max, category: GradeCategory.MIDTERM, weight: 30, due_date: null,
    due_time: null, duration_minutes: null, schedule_as: GradeSchedule.TASK, excluded: false,
    subcategory_weight: share,
  };
}

const even = [grade("m1", "M1", 48, 52), grade("m2", "M2", 40, 80), grade("m3", "M3", 27, 30)];
const split = [grade("m1", "M1", 48, 52, 10), grade("m2", "M2", 40, 80, 5), grade("m3", "M3", 27, 30, 15)];

beforeEach(() => {
  api.setSubcategoryWeights.mockReset();
  api.setSubcategoryWeights.mockResolvedValue([]);
});
afterEach(cleanup);

function openModal(items: Grade[], onSaved = vi.fn()) {
  render(
    <SubcategoryWeightsModal
      open courseId="c1" category={GradeCategory.MIDTERM} categoryWeight={30} items={items}
      onClose={() => {}} onSaved={onSaved}
    />
  );
  return onSaved;
}

function share(name: string): HTMLInputElement {
  return screen.getByLabelText(name) as HTMLInputElement;
}

describe("the split helpers", () => {
  it("shares evenly to the cent", () => {
    expect(evenSplit(20, 3)).toEqual([6.66, 6.67, 6.67]);
    expect(addsUp(evenSplit(20, 3), 20)).toBe(true);
    expect(addsUp([10, 5, 10], 30)).toBe(false);
  });
});

describe("SubcategoryWeightsModal", () => {
  it("starts an even category at its even share", () => {
    openModal(even);

    expect([share("M1").value, share("M2").value, share("M3").value]).toEqual(["10", "10", "10"]);
    expect(screen.getByRole("status").textContent).toBe("Adds up to 30%.");
  });

  it("won't save a split that doesn't add up", () => {
    openModal(even);

    fireEvent.change(share("M3"), { target: { value: "5" } });

    expect(screen.getByRole("status").textContent).toBe("Adds up to 25%: 5% left to share.");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(share("M3"), { target: { value: "15" } });
    expect(screen.getByRole("status").textContent).toBe("Adds up to 35%: 5% too much.");
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("saves a split that adds up, by grade id", async () => {
    const onSaved = openModal(even);

    fireEvent.change(share("M2"), { target: { value: "5" } });
    fireEvent.change(share("M3"), { target: { value: "15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.setSubcategoryWeights).toHaveBeenCalledWith("u1", "c1", "Midterm", { m1: 10, m2: 5, m3: 15 });
  });

  it("offers to share evenly again only when split, and sends null", async () => {
    openModal(even);
    expect(screen.queryByRole("button", { name: "Share evenly again" })).toBeNull();
    cleanup();

    const onSaved = openModal(split);
    expect([share("M1").value, share("M2").value, share("M3").value]).toEqual(["10", "5", "15"]);
    fireEvent.click(screen.getByRole("button", { name: "Share evenly again" }));

    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    expect(api.setSubcategoryWeights).toHaveBeenCalledWith("u1", "c1", "Midterm", null);
  });

  it("shows the server's refusal", async () => {
    api.setSubcategoryWeights.mockRejectedValue(new Error("Subcategory weights must add up to Midterm's 30%"));
    openModal(split);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText(/must add up to Midterm's 30%/)).toBeTruthy();
  });
});

function column(items: Grade[], weight = 30) {
  const onSplit = vi.fn();
  render(
    <GradeCategoryColumn
      title="Midterm" category={GradeCategory.MIDTERM} categoryWeight={weight} items={items}
      onEditItem={() => {}} onAddGrade={() => {}} onDeleteItem={() => {}} onSplit={onSplit}
    />
  );
  return onSplit;
}

describe("GradeCategoryColumn and subcategory weights", () => {
  it("says an even category shares its weight evenly, with no share on the rows", () => {
    column(even);

    expect(screen.getByText("30% shared evenly")).toBeTruthy();
    expect(screen.queryByText("10%")).toBeNull();
  });

  it("shows each item's share when split", () => {
    column(split);

    expect(screen.getByText("Split by subcategory weights")).toBeTruthy();
    expect(screen.getByText("5%")).toBeTruthy();
    expect(screen.getByText("15%")).toBeTruthy();
  });

  it("opens the split from its button", () => {
    const onSplit = column(even);

    fireEvent.click(screen.getByRole("button", { name: "Split Midterm's 30%" }));

    expect(onSplit).toHaveBeenCalledWith("Midterm");
  });

  it("explains the rules behind a ? mark", () => {
    column(even);

    fireEvent.click(screen.getByRole("button", { name: "What subcategory weights are" }));

    const note = screen.getByRole("note");
    expect(note.textContent).toContain("They must add up to 30%");
    expect(note.textContent).toContain("shared evenly: every item counts the same, whatever it's out of");
  });

  it("warns about an item at 0% of a split", () => {
    column([...split.slice(0, 2), grade("m3", "M3", 27, 30, 0), grade("m4", "M4", null, 40, 0)]);

    expect(screen.getByText(/M3, M4 are at 0%, so they don't count yet/)).toBeTruthy();
  });

  it("has nothing to split in a category with no weight", () => {
    column(even, 0);

    expect(screen.queryByRole("button", { name: /Split/ })).toBeNull();
  });
});

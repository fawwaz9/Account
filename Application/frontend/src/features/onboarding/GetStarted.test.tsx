// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import GetStarted, { steps, StepInputs } from "./GetStarted";

const fresh: StepInputs = {
  termSet: false, zone: "America/Regina", browserZone: "America/Vancouver",
  courseCount: 0, hasMoney: false, hasWeek: false,
};
const settled: StepInputs = {
  termSet: true, zone: "America/Vancouver", browserZone: "America/Vancouver",
  courseCount: 4, hasMoney: true, hasWeek: true,
};

function show(inputs: StepInputs) {
  return render(
    <MemoryRouter>
      <GetStarted userId="u1" steps={steps(inputs)} />
    </MemoryRouter>,
  );
}

beforeEach(() => installStorage());
afterEach(cleanup);

/** jsdom under this Node has no usable localStorage; a fresh in-memory one per test. */
function installStorage() {
  const data = new Map<string, string>();
  const storage = {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, String(value)),
    removeItem: (key: string) => void data.delete(key),
    clear: () => data.clear(),
    key: (index: number) => [...data.keys()][index] ?? null,
    get length() { return data.size; },
  };
  Object.defineProperty(window, "localStorage", { value: storage, configurable: true });
}


describe("steps", () => {
  it("a brand new account has all five to do", () => {
    expect(steps(fresh).filter((s) => !s.done)).toHaveLength(5);
  });

  it("each step is done once the thing exists, however it was added", () => {
    expect(steps(settled).every((s) => s.done)).toBe(true);
  });

  it("the time zone is done when it matches the browser's", () => {
    const zone = (inputs: StepInputs) => steps(inputs).find((s) => s.id === "zone")!.done;
    expect(zone(fresh)).toBe(false);
    expect(zone({ ...fresh, zone: "America/Vancouver" })).toBe(true);
    // A browser that will not say is no reason to nag.
    expect(zone({ ...fresh, browserZone: undefined })).toBe(true);
  });
});

describe("GetStarted", () => {
  it("links every step still to do, straight to where it is done", () => {
    show(fresh);
    expect(screen.getByRole("link", { name: "Add your courses" }).getAttribute("href")).toBe("/grades");
    expect(screen.getByRole("link", { name: "Check your time zone" }).getAttribute("href"))
      .toBe("/settings?tab=calendar");
    expect(screen.getByText("0 of 5")).toBeTruthy();
  });

  it("a finished step is ticked, and is not a link any more", () => {
    show({ ...fresh, courseCount: 2 });
    expect(screen.queryByRole("link", { name: "Add your courses" })).toBeNull();
    expect(screen.getByText("1 of 5")).toBeTruthy();
  });

  it("is gone once everything is done", () => {
    const { container } = show(settled);
    expect(container.textContent).toBe("");
  });

  it("still hides, for this visit, where storage is refused", () => {
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      get() { throw new Error("SecurityError"); },
    });
    show(fresh);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByRole("heading", { name: /Get started/ })).toBeNull();
  });

  it("hides when asked, and stays hidden for that user", () => {
    show(fresh);
    fireEvent.click(screen.getByRole("button", { name: "Hide" }));
    expect(screen.queryByText("Get started")).toBeNull();

    cleanup();
    show(fresh);
    expect(screen.queryByRole("heading", { name: /Get started/ })).toBeNull();
  });
});

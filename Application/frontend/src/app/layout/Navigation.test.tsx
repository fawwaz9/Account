// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sidebar, { NAV } from "./Sidebar";
import BottomNav, { PHONE_NAV, PHONE_NAV_ORDER } from "./BottomNav";

/**
 * The two navigation bars: the desktop sidebar and the phone's bottom icon bar
 * from the owner's sketch. One list feeds both, so an icon or a label cannot
 * differ between them.
 */

afterEach(cleanup);

const ICON_FILES = ["home_m", "grades_m", "calendar_m", "tasks_m", "jobs_m", "fitness_m", "budget_m",
  "settings_m", "profile_m"];

describe("the icons", () => {
  it("are all in the assets folder", () => {
    for (const name of ICON_FILES) {
      expect(existsSync(join(__dirname, `../../assets/icons/${name}.png`)), name).toBe(true);
    }
  });

  it("give every page in the nav its own icon", () => {
    const icons = NAV.map((item) => item.icon);
    expect(icons.every(Boolean)).toBe(true);
    expect(new Set(icons).size).toBe(NAV.length);
  });
});

describe("the phone's bottom bar", () => {
  function showAt(path: string) {
    return render(<MemoryRouter initialEntries={[path]}><BottomNav /></MemoryRouter>);
  }

  it("runs in the sketched order: home, grades, tasks, budget, calendar, fitness, jobs", () => {
    showAt("/");
    const names = within(screen.getByRole("navigation")).getAllByRole("link")
      .map((link) => link.getAttribute("aria-label"));
    expect(names).toEqual(["Dashboard", "Grades", "Tasks", "Budget", "Calendar", "Fitness", "Jobs"]);
  });

  it("leaves Settings to the profile icon", () => {
    showAt("/");
    expect(screen.queryByRole("link", { name: "Settings" })).toBeNull();
  });

  it("takes each entry from the sidebar's list, icon and all", () => {
    expect(PHONE_NAV.map((item) => item.to)).toEqual(PHONE_NAV_ORDER);
    for (const item of PHONE_NAV) expect(NAV).toContain(item);
  });

  it("draws an icon in every link and names each one", () => {
    const { container } = showAt("/");
    const links = container.querySelectorAll(".phoneNavLink");
    expect(links).toHaveLength(7);
    for (const link of links) {
      expect(link.querySelector(".appIcon")).not.toBeNull();
      expect(link.getAttribute("aria-label")).toBeTruthy();
    }
  });

  it("marks the page you are on, and only that page", () => {
    showAt("/calendar");
    const current = screen.getAllByRole("link").filter((link) => link.getAttribute("aria-current") === "page");
    expect(current.map((link) => link.getAttribute("aria-label"))).toEqual(["Calendar"]);
  });

  it("scrolls the current page's icon into view, since Fitness and Jobs start past the edge", () => {
    const scrolled: string[] = [];
    const original = Element.prototype.scrollIntoView;
    Element.prototype.scrollIntoView = vi.fn(function (this: Element) {
      scrolled.push(this.getAttribute("aria-label") ?? "");
    });
    try {
      showAt("/jobs/applications");
      expect(scrolled).toEqual(["Jobs"]);
    } finally {
      Element.prototype.scrollIntoView = original;
    }
  });

  it("does not mark home as current on every page beneath it", () => {
    showAt("/grades");
    expect(screen.getByRole("link", { name: "Dashboard" }).getAttribute("aria-current")).toBeNull();
  });
});

describe("the desktop sidebar", () => {
  it("keeps every label, with a gold icon before it", () => {
    render(<MemoryRouter><Sidebar /></MemoryRouter>);
    for (const item of NAV) {
      const link = screen.getByRole("link", { name: item.label });
      expect(link.querySelector(".appIcon")).not.toBeNull();
    }
  });
});

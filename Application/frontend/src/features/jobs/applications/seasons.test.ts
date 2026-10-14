import { describe, expect, it } from "vitest";
import { defaultSeason, monthLabel, seasonSpan } from "./seasons";
import { Season } from "./types";

/** D7: what the page opens on, and how a season's months read. */

const s = (id: string, starts: string, ends: string): Season => ({ id, name: id, starts, ends });

describe("the season the page opens on", () => {
  it("is the one whose months include today", () => {
    expect(defaultSeason([s("summer", "2026-05", "2026-08"), s("fall", "2026-09", "2026-12")], "2026-10-13")?.id)
      .toBe("fall");
  });

  it("counts the end month whole", () => {
    // With the end month left out, nothing would include today and the fallback
    // would pick "next", which ends later -- so this can't pass by accident.
    expect(defaultSeason([s("fall", "2026-09", "2026-10"), s("next", "2026-11", "2026-12")], "2026-10-31")?.id)
      .toBe("fall");
  });

  it("prefers the one that started latest when two include today", () => {
    expect(defaultSeason([s("year", "2026-01", "2026-12"), s("winter", "2026-09", "2026-11")], "2026-10-13")?.id)
      .toBe("winter");
  });

  it("falls back to the most recent when none includes today", () => {
    expect(defaultSeason([s("old", "2025-09", "2025-12"), s("recent", "2026-05", "2026-08")], "2026-10-13")?.id)
      .toBe("recent");
  });

  it("is all time when there are no seasons", () => {
    expect(defaultSeason([], "2026-10-13")).toBeNull();
  });
});

describe("a season's months", () => {
  it("read as month and year", () => {
    expect(monthLabel("2026-09")).toBe("Sep 2026");
    expect(seasonSpan({ starts: "2026-09", ends: "2027-01" })).toBe("Sep 2026 – Jan 2027");
  });

  it("read once for a single month", () => {
    expect(seasonSpan({ starts: "2026-09", ends: "2026-09" })).toBe("Sep 2026");
  });
});

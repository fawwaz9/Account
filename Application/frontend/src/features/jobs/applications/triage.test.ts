import { describe, expect, it } from "vitest";
import { arrange, dueSoon, matches } from "./triage";
import { Application } from "./types";

/** What the tracker lists unasked, and what search finds (D9). */

const TODAY = "2026-10-14";

function application(over: Partial<Application>): Application {
  return {
    id: "a", company: "Shopify", role: "Backend intern", applied_on: "2026-09-01", source: null, link: null,
    location: null, notes: null, status: "applied", deadline: null, follow_up_on: null, offer_amount: null,
    offer_period: null, steps: [], last_step_on: "2026-10-10", quiet: false, created_at: null, updated_at: null,
    ...over,
  };
}

const ids = (list: Application[]) => list.map((item) => item.id);

describe("needs you", () => {
  it("holds offers, interviews and screenings, in that order", () => {
    const { needsYou } = arrange([
      application({ id: "s", status: "screening" }), application({ id: "o", status: "offer" }),
      application({ id: "i", status: "interview" }),
    ], TODAY);
    expect(ids(needsYou)).toEqual(["o", "i", "s"]);
  });

  it("keeps an interview there even once it goes quiet", () => {
    const { needsYou, quiet } = arrange([application({ id: "i", status: "interview", quiet: true })], TODAY);
    expect(ids(needsYou)).toEqual(["i"]);
    expect(quiet).toEqual([]);
  });

  it("takes a plain application with a date coming up, soonest first, after the active ones", () => {
    const { needsYou } = arrange([
      application({ id: "later", deadline: "2026-10-25" }), application({ id: "soon", follow_up_on: "2026-10-16" }),
      application({ id: "i", status: "interview" }),
    ], TODAY);
    expect(ids(needsYou)).toEqual(["i", "soon", "later"]);
  });

  it("counts a deadline in the next 14 days, not a passed one or one further out", () => {
    expect(dueSoon(application({ deadline: TODAY }), TODAY)).toBe(true);
    expect(dueSoon(application({ deadline: "2026-10-28" }), TODAY)).toBe(true);
    expect(dueSoon(application({ deadline: "2026-10-29" }), TODAY)).toBe(false);
    expect(dueSoon(application({ deadline: "2026-10-13" }), TODAY)).toBe(false);
  });

  it("counts a follow-up due within a week, and an overdue one", () => {
    expect(dueSoon(application({ follow_up_on: "2026-10-21" }), TODAY)).toBe(true);
    expect(dueSoon(application({ follow_up_on: "2026-10-22" }), TODAY)).toBe(false);
    expect(dueSoon(application({ follow_up_on: "2026-09-30" }), TODAY)).toBe(true);
  });
});

describe("the rest", () => {
  it("puts quiet ones apart, longest silent first", () => {
    const { quiet, needsYou } = arrange([
      application({ id: "recent", quiet: true, last_step_on: "2026-09-10" }),
      application({ id: "old", quiet: true, last_step_on: "2026-08-01" }),
    ], TODAY);
    expect(ids(quiet)).toEqual(["old", "recent"]);
    expect(needsYou).toEqual([]);
  });

  it("leaves a new application with nothing due as waiting", () => {
    expect(ids(arrange([application({ id: "w" })], TODAY).waiting)).toEqual(["w"]);
  });

  it("files every closed status as finished, whatever its dates", () => {
    const closed = (["accepted", "rejected", "no_reply", "withdrawn"] as const).map((status) =>
      application({ id: status, status, follow_up_on: TODAY }));
    const { finished, needsYou } = arrange(closed, TODAY);
    expect(ids(finished)).toEqual(["accepted", "rejected", "no_reply", "withdrawn"]);
    expect(needsYou).toEqual([]);
  });

  it("puts each application in exactly one group", () => {
    const all = [
      application({ id: "1", status: "offer" }), application({ id: "2", quiet: true }),
      application({ id: "3" }), application({ id: "4", status: "rejected" }),
      application({ id: "5", quiet: true, deadline: "2026-10-20" }),
    ];
    const { needsYou, quiet, waiting, finished } = arrange(all, TODAY);
    expect([...needsYou, ...quiet, ...waiting, ...finished].map((item) => item.id).sort()).toEqual(["1", "2", "3", "4", "5"]);
    expect(ids(needsYou)).toContain("5");
  });
});

describe("search", () => {
  const item = application({ company: "EA Vancouver", role: "Game programmer co-op", location: "Burnaby", source: "SCOPE" });

  it("matches company, role, location and source, ignoring case", () => {
    for (const query of ["ea van", "PROGRAMMER", "burnaby", "scope"]) expect(matches(item, query), query).toBe(true);
  });

  it("needs every word to match", () => {
    expect(matches(item, "game burnaby")).toBe(true);
    expect(matches(item, "game toronto")).toBe(false);
  });

  it("matches nothing until something is typed", () => {
    expect(matches(item, "")).toBe(false);
    expect(matches(item, "   ")).toBe(false);
  });

  it("does not search the notes", () => {
    expect(matches(application({ notes: "secret referral" }), "secret")).toBe(false);
  });
});

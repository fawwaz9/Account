import { describe, expect, it } from "vitest";
import { applicationOccurrences } from "./useCalender";
import { Application } from "../../jobs/applications/types";

/** D4: an application's deadline and follow-up, as all-day items on the calendar. */

function application(over: Partial<Application> = {}): Application {
  return {
    id: "a1", company: "Shopify", role: "Backend intern", applied_on: "2026-10-01", source: null, link: null,
    location: null, notes: null, status: "applied", deadline: "2026-10-14", follow_up_on: "2026-10-20",
    offer_amount: null, offer_period: null, steps: [], last_step_on: "2026-10-01", quiet: false, salary_shared: false,
    created_at: null, updated_at: null, ...over,
  };
}

describe("application dates on the calendar", () => {
  it("shows the deadline and the follow-up inside the window", () => {
    const items = applicationOccurrences([application()], "2026-10-12", "2026-10-25");
    expect(items.map((item) => [item.on_date, item.title])).toEqual([
      ["2026-10-14", "Deadline: Shopify"], ["2026-10-20", "Follow up: Shopify"],
    ]);
    expect(items[0].application).toEqual({ id: "a1", what: "deadline", company: "Shopify", role: "Backend intern" });
    expect(items[0].start_time).toBeNull();
  });

  it("leaves out a date outside the window", () => {
    expect(applicationOccurrences([application()], "2026-10-15", "2026-10-18")).toEqual([]);
  });

  it("leaves out a finished application's dates: there is nothing left to do", () => {
    for (const status of ["accepted", "rejected", "no_reply", "withdrawn"] as const) {
      expect(applicationOccurrences([application({ status })], "2026-10-01", "2026-10-31"), status).toEqual([]);
    }
  });

  it("keeps an offer's, which still waits on you", () => {
    expect(applicationOccurrences([application({ status: "offer" })], "2026-10-01", "2026-10-31")).toHaveLength(2);
  });

  it("gives each date its own id, so the two never collide", () => {
    const ids = applicationOccurrences([application()], "2026-10-01", "2026-10-31").map((item) => item.event_id);
    expect(new Set(ids).size).toBe(2);
  });
});

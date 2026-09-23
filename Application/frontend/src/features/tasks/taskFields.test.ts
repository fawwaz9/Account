import { describe, expect, it } from "vitest";
import { numberOrNull, parseTags, tagText, withDueDate } from "./taskFields";
import { END_OF_DAY } from "./dueTime";

/**
 * These rules exist in one place because two forms hold them -- the inline add
 * row and the edit dialog -- and both fail silently when they drift: one
 * produces a save the API rejects, the other quietly drops what was typed.
 */
describe("withDueDate", () => {
  it("pre-fills the end of the day, since a bare deadline means by then", () => {
    expect(withDueDate({ due_date: null, due_time: null }, "2026-09-08")).toEqual({
      due_date: "2026-09-08",
      due_time: END_OF_DAY,
    });
  });

  it("keeps a time the student already chose", () => {
    expect(withDueDate({ due_date: "2026-09-08", due_time: "09:00" }, "2026-09-09")).toEqual({
      due_date: "2026-09-09",
      due_time: "09:00",
    });
  });

  /**
   * The API refuses a time with no date -- "A time of day needs a date to go
   * with it" -- so clearing one has to clear the other, or the next save is
   * rejected for a field the student cannot see.
   */
  it("clears the time when the date goes", () => {
    expect(withDueDate({ due_date: "2026-09-08", due_time: "09:00" }, null)).toEqual({
      due_date: null,
      due_time: null,
    });
  });

  it("leaves every other field alone", () => {
    const before = { due_date: null, due_time: null, title: "Lab 3", priority: 4 };

    expect(withDueDate(before, "2026-09-08")).toMatchObject({ title: "Lab 3", priority: 4 });
  });
});

describe("parseTags", () => {
  it("splits, trims, and drops the blanks a trailing comma leaves", () => {
    expect(parseTags("reading, cpsc 221 , ,lab")).toEqual(["reading", "cpsc 221", "lab"]);
  });

  it("is empty for an empty box rather than one empty tag", () => {
    // An empty tag renders as a stray chip nothing can remove.
    expect(parseTags("")).toEqual([]);
    expect(parseTags("   ")).toEqual([]);
    expect(parseTags(",,,")).toEqual([]);
  });

  it("round-trips through tagText", () => {
    const tags = ["reading", "cpsc 221", "lab"];

    expect(parseTags(tagText(tags))).toEqual(tags);
  });
});

/**
 * `Number("")` is 0, so reading a number box directly records "takes no time"
 * where the student meant "no estimate given" -- and a zero-minute estimate is
 * counted in the week's hours as a task that costs nothing.
 */
describe("numberOrNull", () => {
  it("is null for an empty box, not zero", () => {
    expect(numberOrNull("")).toBeNull();
  });

  it("keeps a real zero", () => {
    expect(numberOrNull("0")).toBe(0);
  });

  it("reads an ordinary number", () => {
    expect(numberOrNull("45")).toBe(45);
    expect(numberOrNull("2.5")).toBe(2.5);
  });
});

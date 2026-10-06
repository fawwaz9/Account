// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render } from "@testing-library/react";
import ProjectionReview from "./ProjectionReview";
import type { Course } from "../types";

const base = { final_grade: 0, projected_before_final: null, projected_on: null } as unknown as Course;
const show = (fields: Partial<Course>) => render(<ProjectionReview course={{ ...base, ...fields }} />).container;

afterEach(cleanup);

describe("ProjectionReview", () => {
  it("sets the projection against the result, with the day it stood", () => {
    const text = show({ final_grade: 82, projected_before_final: 83, projected_on: "2026-12-10" }).textContent;
    expect(text).toMatch(/^On .*10.*, before the final, we projected 83\.0%\. You got 82%, 1\.0 below it\.$/);
  });

  it("says above, and exactly", () => {
    expect(show({ final_grade: 90, projected_before_final: 85.55 }).textContent)
      .toBe("Before the final, we projected 85.5%. You got 90%, 4.5 above it.");
    expect(show({ final_grade: 85, projected_before_final: 85 }).textContent).toContain("exactly as projected");
  });

  it("says nothing until both exist", () => {
    expect(show({ final_grade: 82 }).textContent).toBe("");
    expect(show({ projected_before_final: 83 }).textContent).toBe("");
  });
});

// @vitest-environment jsdom
import { afterEach, describe, expect, it } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import ExamCountdownCard, { whenText } from "./ExamCountdownCard";
import { CountdownExam, ExamCountdown } from "../types";

/** Phase 4 item 5: inside a week of an exam, its course's work comes first. */

function exam(over: Partial<CountdownExam> = {}): CountdownExam {
  return {
    event_id: "e1", title: "Midterm 2", kind: "midterm", on_date: "2099-01-04", start_time: "18:30:00",
    location: null, course_id: "c1", course_code: "CPSC 310", days_left: 3,
    tasks: [{ id: "t1", title: "Practice midterm", due_date: null, estimated_minutes: 90, priority: 4 }],
    open_tasks: 1, estimated_minutes: 90,
    ...over,
  };
}

function countdown(exams: CountdownExam[]): ExamCountdown {
  return { window_days: 7, exams };
}

afterEach(cleanup);

describe("ExamCountdownCard", () => {
  it("names the exam, how far off it is, and its course's work", () => {
    render(<ExamCountdownCard countdown={countdown([exam()])} />);

    expect(screen.getByText("In 3 days")).toBeTruthy();
    expect(screen.getByText("CPSC 310 Midterm")).toBeTruthy();
    expect(screen.getByText("Practice midterm")).toBeTruthy();
    expect(screen.getByText(/1 open task due by then · about 1h 30m estimated/)).toBeTruthy();
  });

  it("says how many more are in the list when it shows only some", () => {
    render(<ExamCountdownCard countdown={countdown([exam({ open_tasks: 8 })])} />);

    expect(screen.getByText(/8 open tasks due by then, 7 more in the list below/)).toBeTruthy();
  });

  it("says when nothing is open before it, or the exam has no course", () => {
    render(<ExamCountdownCard countdown={countdown([
      exam({ event_id: "a", tasks: [], open_tasks: 0, estimated_minutes: 0 }),
      exam({ event_id: "b", course_id: null, course_code: null, tasks: [], open_tasks: 0, estimated_minutes: 0 }),
    ])} />);

    expect(screen.getByText("Nothing open on this course before it.")).toBeTruthy();
    expect(screen.getByText("Not linked to a course.")).toBeTruthy();
  });

  it("renders nothing with no exam inside the week", () => {
    const { container } = render(<ExamCountdownCard countdown={countdown([])} />);

    expect(container.textContent).toBe("");
  });

  it("reads today and tomorrow in words", () => {
    expect([whenText(0), whenText(1), whenText(5)]).toEqual(["Today", "Tomorrow", "In 5 days"]);
  });
});

// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import HowLongPrompt from "./HowLongPrompt";
import EstimateRatioCard from "./EstimateRatioCard";
import TaskItem from "./TaskItem";
import WorkloadHeadline from "../../calender/components/WorkloadHeadline";
import { duration } from "../../../shared/utils/dateUtils";
import type { EstimateRatio, Task } from "../types";

const essay = {
  id: "t1", title: "Essay", notes: null, due_date: null, due_time: null, estimated_minutes: 120,
  course_id: null, course_code: null, tags: [], priority: 3, done: true, completed_at: null,
  archived: true, created_at: null, grade_id: null, recurring_id: null, risk: null,
  snoozed_until: null, snooze_count: 0, last_snooze_reason: null, actual_minutes: null, timer_started_at: null,
} as Task;

afterEach(cleanup);

describe("HowLongPrompt", () => {
  it("offers the estimate and its multiples, and answers with the minutes", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(<HowLongPrompt task={essay} onAnswer={onAnswer} onSkip={vi.fn()} />);
    const labels = screen.getAllByRole("button").map((b) => b.textContent);
    expect(labels).toEqual(expect.arrayContaining([
      `As estimated · ${duration(120)}`, `Half · ${duration(60)}`, `1.5× · ${duration(180)}`, `2× · ${duration(240)}`,
    ]));
    fireEvent.click(screen.getByRole("button", { name: `1.5× · ${duration(180)}` }));
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(180));
  });

  it("offers the timer's total first when one ran", () => {
    render(<HowLongPrompt task={{ ...essay, actual_minutes: 40 }} onAnswer={vi.fn()} onSkip={vi.fn()} />);
    expect(screen.getAllByRole("button")[0].textContent).toBe(`Keep the timer's ${duration(40)}`);
    expect(screen.getByText(/The timer measured/)).toBeTruthy();
  });

  it("takes typed whole minutes in range only", async () => {
    const onAnswer = vi.fn().mockResolvedValue(undefined);
    render(<HowLongPrompt task={essay} onAnswer={onAnswer} onSkip={vi.fn()} />);
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    const input = screen.getByLabelText("Minutes");
    for (const bad of ["", "0", "2.5", "2401"]) {
      fireEvent.change(input, { target: { value: bad } });
      expect(save.disabled).toBe(true);
    }
    fireEvent.change(input, { target: { value: "95" } });
    fireEvent.click(save);
    await waitFor(() => expect(onAnswer).toHaveBeenCalledWith(95));
  });

  it("says a failure and lets the answer be tried again; skip answers nothing", async () => {
    const onAnswer = vi.fn().mockRejectedValue(new Error("Task not found"));
    const onSkip = vi.fn();
    render(<HowLongPrompt task={essay} onAnswer={onAnswer} onSkip={onSkip} />);
    fireEvent.click(screen.getByRole("button", { name: `As estimated · ${duration(120)}` }));
    expect((await screen.findByRole("alert")).textContent).toBe("Task not found");
    fireEvent.click(screen.getByRole("button", { name: "Skip" }));
    expect(onSkip).toHaveBeenCalled();
  });
});

const ratio = (fields: Partial<EstimateRatio>): EstimateRatio =>
  ({ ratio: null, tasks: 0, needed: 5, estimated_minutes: 0, actual_minutes: 0, applied: false, ...fields });

describe("EstimateRatioCard", () => {
  it("is absent with nothing timed, and counts towards the ratio before it has one", () => {
    const { container } = render(<EstimateRatioCard ratio={ratio({})} onApply={vi.fn()} />);
    expect(container.textContent).toBe("");
    cleanup();
    render(<EstimateRatioCard ratio={ratio({ tasks: 3 })} onApply={vi.fn()} />);
    expect(screen.getByText(/3 of 5 finished tasks/)).toBeTruthy();
    expect(screen.queryByRole("checkbox")).toBeNull();
  });

  it("states the ratio and switches the forecast's use of it", async () => {
    const onApply = vi.fn().mockResolvedValue(undefined);
    render(<EstimateRatioCard ratio={ratio({ ratio: 1.4, tasks: 12 })} onApply={onApply} />);
    expect(screen.getByText(/take 1\.40× your estimates, across 12 finished/)).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox", { name: "Use it in the workload forecast" }));
    await waitFor(() => expect(onApply).toHaveBeenCalledWith(true));
  });

  it("says when a switch fails", async () => {
    render(<EstimateRatioCard ratio={ratio({ ratio: 0.8, tasks: 6, applied: true })}
                              onApply={vi.fn().mockRejectedValue(new Error("Offline"))} />);
    expect(screen.getByText(/less than you think/)).toBeTruthy();
    fireEvent.click(screen.getByRole("checkbox"));
    expect((await screen.findByRole("alert")).textContent).toBe("Offline");
  });
});

describe("TaskItem timer", () => {
  const handlers = { onToggle: vi.fn(), onEdit: vi.fn(), onDelete: vi.fn(), onPriority: vi.fn(),
                     onSnooze: vi.fn(), onWake: vi.fn() };
  const open = { ...essay, done: false, archived: false };

  it("offers Time on an open task, and Stop with the start while one runs", () => {
    const onTimer = vi.fn();
    render(<ul><TaskItem task={open} {...handlers} onTimer={onTimer} busy={false} /></ul>);
    fireEvent.click(screen.getByRole("button", { name: "Time Essay" }));
    expect(onTimer).toHaveBeenCalledWith(open);
    cleanup();
    render(<ul><TaskItem task={{ ...open, timer_started_at: "2026-10-06T12:05:00" }} {...handlers}
                         onTimer={onTimer} busy={false} /></ul>);
    expect(screen.getByRole("button", { name: "Stop timing Essay" }).getAttribute("aria-pressed")).toBe("true");
    expect(screen.getByRole("status").textContent).toMatch(/^timing since /);
  });

  it("has no timer on a finished task or without the handler, and shows what it took", () => {
    render(<ul><TaskItem task={{ ...essay, actual_minutes: 90 }} {...handlers} onTimer={vi.fn()} busy={false} /></ul>);
    expect(screen.queryByRole("button", { name: /Time|Stop timing/ })).toBeNull();
    expect(screen.getByText(`took ${duration(90)}`)).toBeTruthy();
    cleanup();
    render(<ul><TaskItem task={{ ...essay, done: false }} {...handlers} busy={false} /></ul>);
    expect(screen.queryByRole("button", { name: /^Time / })).toBeNull();
  });
});

describe("WorkloadHeadline with the ratio", () => {
  it("says the figure is scaled, from what, and where to turn it off", () => {
    render(<WorkloadHeadline forecast={{ estimatedMinutes: 168, taskCount: 2, unestimatedTasks: 0,
                                         freeMinutes: 600, estimateRatio: 1.4, typedMinutes: 120 }} />);
    expect(screen.getByText(new RegExp(`Your estimates \\(${duration(120)}\\) × 1\\.40`))).toBeTruthy();
    expect(screen.getByText(/Turn it off on Tasks/)).toBeTruthy();
  });

  it("says nothing of a ratio that is not in use", () => {
    const { container } = render(<WorkloadHeadline forecast={{ estimatedMinutes: 120, taskCount: 2,
      unestimatedTasks: 0, freeMinutes: 600, estimateRatio: null, typedMinutes: 120 }} />);
    expect(container.textContent).not.toContain("×");
  });
});

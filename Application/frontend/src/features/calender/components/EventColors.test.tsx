// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import EventColors from "./EventColors";
import { DEFAULT_KIND_COLORS } from "../kindColors";

afterEach(cleanup);

describe("EventColors", () => {
  it("shows each kind's default when nothing was chosen", () => {
    render(<EventColors colors={{}} onChange={() => {}} />);
    expect((screen.getByLabelText("Midterm") as HTMLInputElement).value).toBe(DEFAULT_KIND_COLORS.midterm);
  });

  it("draws an exam sample with the exam's heavier styling", () => {
    // The point of drawing a real chip: an exam still looks like an exam.
    const { container } = render(<EventColors colors={{}} onChange={() => {}} />);
    expect(container.querySelector(".kindColorSample.calChip-final")!.classList).toContain("calChipExam");
    expect(container.querySelector(".kindColorSample.calChip-lab")!.classList).not.toContain("calChipExam");
  });

  it("reports a pick lowercased, keeping the other choices", () => {
    const onChange = vi.fn();
    render(<EventColors colors={{ lab: "#010203" }} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Lecture"), { target: { value: "#ABCDEF" } });
    expect(onChange).toHaveBeenCalledWith({ lab: "#010203", lecture: "#abcdef" });
  });

  it("removes a kind on Default rather than storing the default's value", () => {
    const onChange = vi.fn();
    render(<EventColors colors={{ lab: "#010203" }} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: /default colour for Lab/ }));
    expect(onChange).toHaveBeenCalledWith({});
  });

  it("keeps the sample out of the accessibility tree", () => {
    const { container } = render(<EventColors colors={{}} onChange={() => {}} />);
    for (const sample of container.querySelectorAll(".kindColorSample")) {
      expect(sample.getAttribute("aria-hidden")).toBe("true");
    }
  });
});

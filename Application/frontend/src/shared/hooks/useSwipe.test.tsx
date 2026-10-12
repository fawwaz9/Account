// @vitest-environment jsdom
import { cleanup, fireEvent, render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useSwipe } from "./useSwipe";

/**
 * A sideways swipe steps the calendar on a phone. Scrolling the hours is a
 * vertical drag that is never perfectly vertical, so only clearly sideways
 * movement may count.
 */

function Surface({ onSwipe, enabled = true }: { onSwipe: (d: 1 | -1) => void; enabled?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useSwipe(ref, onSwipe, enabled);
  return <div ref={ref} data-testid="surface" />;
}

function drag(element: Element, dx: number, dy: number) {
  fireEvent.touchStart(element, { touches: [{ clientX: 200, clientY: 300 }] });
  fireEvent.touchEnd(element, { changedTouches: [{ clientX: 200 + dx, clientY: 300 + dy }] });
}

afterEach(cleanup);

describe("a swipe", () => {
  it("to the left steps forward", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} />);
    drag(getByTestId("surface"), -120, 10);
    expect(onSwipe).toHaveBeenCalledExactlyOnceWith(1);
  });

  it("to the right steps back", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} />);
    drag(getByTestId("surface"), 120, -10);
    expect(onSwipe).toHaveBeenCalledExactlyOnceWith(-1);
  });

  it("does nothing when it is mostly vertical, as a scroll through the hours is", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} />);
    drag(getByTestId("surface"), 80, 200);
    drag(getByTestId("surface"), 70, 50);
    expect(onSwipe).not.toHaveBeenCalled();
  });

  it("does nothing when it is too short to be more than a tap", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} />);
    drag(getByTestId("surface"), -30, 0);
    expect(onSwipe).not.toHaveBeenCalled();
  });

  it("does nothing when two fingers are down, which is a pinch", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} />);
    const surface = getByTestId("surface");
    fireEvent.touchStart(surface, {
      touches: [{ clientX: 200, clientY: 300 }, { clientX: 250, clientY: 300 }],
    });
    fireEvent.touchEnd(surface, { changedTouches: [{ clientX: 50, clientY: 300 }] });
    expect(onSwipe).not.toHaveBeenCalled();
  });

  it("does nothing while switched off, as it is off a phone", () => {
    const onSwipe = vi.fn();
    const { getByTestId } = render(<Surface onSwipe={onSwipe} enabled={false} />);
    drag(getByTestId("surface"), -120, 0);
    expect(onSwipe).not.toHaveBeenCalled();
  });
});

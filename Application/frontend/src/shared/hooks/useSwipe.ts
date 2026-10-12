import { RefObject, useEffect, useRef } from "react";

/** Shortest horizontal travel that counts as a swipe rather than a tap. */
export const SWIPE_DISTANCE = 50;

/** How much more horizontal than vertical a swipe must be. */
const SWIPE_RATIO = 1.5;

/**
 * Call `onSwipe(1)` for a swipe to the left and `onSwipe(-1)` for one to the
 * right -- forward and back, the way a page is turned.
 *
 * Only clearly sideways movement counts, so scrolling through the hours, which
 * is vertical and never perfectly so, cannot step the calendar by accident.
 * The listeners are passive: this only watches, and never holds up a scroll.
 */
export function useSwipe(
  ref: RefObject<HTMLElement | null>,
  onSwipe: (direction: 1 | -1) => void,
  enabled = true
) {
  // Latest handler without re-subscribing every render.
  const latest = useRef(onSwipe);
  latest.current = onSwipe;

  useEffect(() => {
    const element = ref.current;
    if (!enabled || !element) return;

    let start: { x: number; y: number } | null = null;

    function onStart(event: TouchEvent) {
      // A second finger is a pinch, not a swipe.
      start = event.touches.length === 1
        ? { x: event.touches[0].clientX, y: event.touches[0].clientY }
        : null;
    }

    function onEnd(event: TouchEvent) {
      if (!start) return;
      const touch = event.changedTouches[0];
      const dx = touch.clientX - start.x;
      const dy = touch.clientY - start.y;
      start = null;

      if (Math.abs(dx) < SWIPE_DISTANCE || Math.abs(dx) < Math.abs(dy) * SWIPE_RATIO) return;
      latest.current(dx < 0 ? 1 : -1);
    }

    function onCancel() {
      start = null;
    }

    element.addEventListener("touchstart", onStart, { passive: true });
    element.addEventListener("touchend", onEnd, { passive: true });
    element.addEventListener("touchcancel", onCancel, { passive: true });
    return () => {
      element.removeEventListener("touchstart", onStart);
      element.removeEventListener("touchend", onEnd);
      element.removeEventListener("touchcancel", onCancel);
    };
  }, [ref, enabled]);
}

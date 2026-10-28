import { RefObject, useEffect, useRef } from "react";

/** Minimum horizontal travel in pixels for a touch to count as a swipe. */
export const SWIPE_DISTANCE = 50;

/** How many times its vertical travel a swipe's horizontal travel must be. */
const SWIPE_RATIO = 1.5;

/** Call `onSwipe` with 1 for a left swipe and -1 for a right one; one finger, passive listeners. */
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

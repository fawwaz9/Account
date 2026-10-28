import { useEffect, useRef } from "react";

/** Selector for elements whose key presses are typing, not shortcuts. */
const TYPING_TARGETS = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";

/**
 * True when a key press is not a shortcut's: typing, composing, a modifier held,
 * already handled, or any open modal dialog.
 */
export function isTypingContext(event: KeyboardEvent): boolean {
  if (event.isComposing || event.defaultPrevented) return true;
  if (event.metaKey || event.ctrlKey || event.altKey) return true;

  const target = event.target;
  if (target instanceof Element && target.closest(TYPING_TARGETS)) return true;

  return document.querySelector("[aria-modal='true']") !== null;
}

/** Run `handler` on a page-wide press of `key` (letters ignore case) unless the user is typing. */
export function useShortcut(key: string, handler: () => void, enabled = true) {
  // Latest handler without re-subscribing every render: the pages pass inline
  // closures over their own state.
  const latest = useRef(handler);
  latest.current = handler;

  useEffect(() => {
    if (!enabled) return;

    function onKeyDown(event: KeyboardEvent) {
      if (isTypingContext(event)) return;
      const pressed = event.key.length === 1 ? event.key.toLowerCase() : event.key;
      const wanted = key.length === 1 ? key.toLowerCase() : key;
      if (pressed !== wanted) return;
      event.preventDefault();
      latest.current();
    }

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [key, enabled]);
}

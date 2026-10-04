import { useEffect, useRef } from "react";

const TYPING_TARGETS = "input, textarea, select, [contenteditable]:not([contenteditable='false'])";

/**
 * True when a key press belongs to something other than a shortcut.
 *
 * The one guard every shortcut goes through, so "nothing fires while typing" is
 * a single rule rather than a check each page has to remember. A modifier means
 * the key is someone else's (Cmd-K is the omnibox's, Ctrl-R the browser's), and
 * an open dialog owns the keyboard: its fields are inputs anyway, and a bare "n"
 * pressed on its Save button must not open a second form behind it.
 */
export function isTypingContext(event: KeyboardEvent): boolean {
  if (event.isComposing || event.defaultPrevented) return true;
  if (event.metaKey || event.ctrlKey || event.altKey) return true;

  const target = event.target;
  if (target instanceof Element && target.closest(TYPING_TARGETS)) return true;

  return document.querySelector("[aria-modal='true']") !== null;
}

/**
 * Run `handler` when `key` is pressed anywhere on the page, unless the press
 * belongs to typing (see isTypingContext). Matches `event.key`, so letters are
 * compared case-insensitively and "ArrowLeft" works as written.
 */
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

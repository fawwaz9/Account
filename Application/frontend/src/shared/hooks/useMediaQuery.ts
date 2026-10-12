import { useEffect, useState } from "react";

/**
 * Where the app becomes its phone layout: the bottom icon bar, the header with
 * the profile icon, the phone dashboard and the calendar's day and three-day
 * views. The stylesheets switch at the same 720px.
 */
export const PHONE_QUERY = "(max-width: 720px)";

function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(query).matches
    : false;
}

/**
 * Whether a CSS media query matches, kept current as the window changes --
 * a phone rotated, a desktop window narrowed.
 *
 * False where `matchMedia` does not exist (jsdom, very old browsers), so
 * anything gated on it falls back to the desktop behaviour it had before.
 */
export function useMediaQuery(query: string): boolean {
  const [value, setValue] = useState(() => matches(query));

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return;

    const list = window.matchMedia(query);
    const onChange = () => setValue(list.matches);
    // The query may have changed since the first render read it.
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return value;
}

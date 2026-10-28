import { useEffect, useState } from "react";

/** Media query for the phone layout; the stylesheets switch at the same 720px. */
export const PHONE_QUERY = "(max-width: 720px)";

/** Whether `query` matches now; false where `matchMedia` is missing. */
function matches(query: string): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function"
    ? window.matchMedia(query).matches
    : false;
}

/** Live match state of a CSS media query; false without `matchMedia` (jsdom), the desktop path. */
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

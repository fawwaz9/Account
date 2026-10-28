import { useEffect, useRef, useState } from "react";
import { onApiRefresh } from "../../services/apiCache";

/** Call `reload` each time a background refetch changes a cached GET; not on mount. */
export function useApiRefresh(reload: () => unknown): void {
  const latest = useRef(reload);
  latest.current = reload;
  useEffect(() => onApiRefresh(() => { void latest.current(); }), []);
}

/** A counter that rises on each changed background refetch, for an inline effect's deps. */
export function useApiRefreshCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => onApiRefresh(() => setCount((was) => was + 1)), []);
  return count;
}

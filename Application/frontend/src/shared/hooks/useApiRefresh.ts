import { useEffect, useRef, useState } from "react";
import { onApiRefresh } from "../../services/apiCache";

/**
 * Run `reload` whenever a background refetch finds a changed answer (audit
 * #35). The page showed the cached copy at once; this is how it catches up.
 * The reload's own reads come from the just-updated cache, not the network.
 *
 * Not on mount: the hook's own effect does the first load, as it always did.
 */
export function useApiRefresh(reload: () => unknown): void {
  const latest = useRef(reload);
  latest.current = reload;
  useEffect(() => onApiRefresh(() => { void latest.current(); }), []);
}

/**
 * The same, for an effect that fetches inline: a number that goes up on each
 * changed answer, to add to the effect's dependencies.
 */
export function useApiRefreshCount(): number {
  const [count, setCount] = useState(0);
  useEffect(() => onApiRefresh(() => setCount((was) => was + 1)), []);
  return count;
}

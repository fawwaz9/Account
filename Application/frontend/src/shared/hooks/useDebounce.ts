import { useEffect, useState } from "react";

/**
 * Returns `value` only once it has stopped changing for `delay` ms.
 *
 * Used to keep the course search from firing a request on every keystroke.
 */
export function useDebounce<T>(value: T, delay = 250): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}

export default useDebounce;

import { useEffect, useState } from "react";

/** Live match of a CSS media query, e.g. useMedia("(min-width: 1280px)"). */
export function useMedia(query: string): boolean {
  const [match, setMatch] = useState(() => (typeof window === "undefined" ? false : window.matchMedia(query).matches));
  useEffect(() => {
    const m = window.matchMedia(query);
    const on = () => setMatch(m.matches);
    on();
    m.addEventListener("change", on);
    return () => m.removeEventListener("change", on);
  }, [query]);
  return match;
}

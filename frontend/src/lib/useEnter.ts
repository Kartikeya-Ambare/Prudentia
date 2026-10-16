import { useLayoutEffect, useRef, useState, type RefObject } from "react";
import { gsapReady, REDUCED_MOTION } from "@/lib/gsap";

/**
 * The dashboard's entrance for any page: elements marked `data-enter-item` inside the root rise and fade in one after
 * another. Put `data-enter={state}` on the root (the CSS keeps the items hidden while "pending"). A timer reveals
 * everything if GSAP is slow or motion is reduced, so content can never stay invisible.
 */
export function useEnter<T extends HTMLElement>(key: unknown): { ref: RefObject<T | null>; state: "pending" | "done" } {
  const ref = useRef<T>(null);
  const [state, setState] = useState<"pending" | "done">("pending");
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (window.matchMedia(REDUCED_MOTION).matches) { setState("done"); return; }
    setState("pending");
    const items = [...el.querySelectorAll("[data-enter-item]")];
    let cancelled = false;
    let tween: { kill: () => void } | undefined;
    const fallback = setTimeout(() => setState("done"), 1800);
    gsapReady.then(({ gsap }) => {
      if (cancelled) return;
      tween = gsap.fromTo(items, { opacity: 0, y: 16 }, {
        opacity: 1, y: 0, duration: 0.6, ease: "power3.out", stagger: 0.07,
        onComplete: () => { clearTimeout(fallback); setState("done"); },
      });
    });
    return () => { cancelled = true; clearTimeout(fallback); tween?.kill(); };
  }, [key]);
  return { ref, state };
}

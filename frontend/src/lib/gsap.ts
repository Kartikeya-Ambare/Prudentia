/**
 * GSAP core, loaded in its own chunk the first time something animates (the donut sweep, the number
 * count-up), so it never competes with the first paint.
 *
 * Only the core is loaded. ScrollTrigger, ScrollTo and Flip were used by the earlier single-column
 * layout and are no longer needed; add a plugin back here only when a screen really uses it.
 * Not used on purpose: ScrollSmoother (hijacks native scrolling), DrawSVG / MorphSVG / MotionPath
 * (charts are functional, not illustrations), Draggable / Inertia (the slider is a native input, which
 * keeps keyboard and screen-reader support), SplitText / ScrambleText (the count-up is clearer than
 * scrambling digits).
 */
type Loaded = { gsap: typeof import("gsap").gsap };

let loading: Promise<Loaded> | undefined;
const load = () => (loading ??= import("gsap").then(({ gsap }) => ({ gsap })));

/** Thenable: `gsapReady.then(({ gsap }) => ...)` starts the load on first use and shares it after that. */
export const gsapReady: PromiseLike<Loaded> = {
  then: (onOk, onErr) => load().then(onOk, onErr),
};

export const NO_REDUCED_MOTION = "(prefers-reduced-motion: no-preference)";
export const REDUCED_MOTION = "(prefers-reduced-motion: reduce)";

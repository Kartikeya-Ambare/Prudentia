/**
 * Prudie (proo-dee), the mascot of Prudentia.
 * A small violet robot with a glossy screen face, glowing eyes and graphite robot hands.
 *
 * Drawn and animated entirely in code (SVG + springs + 2-bone IK).
 * No images, no Lottie/Rive, no dependencies.
 *
 * Actions:      idle · wave · search · code · thumbsup · look
 * Idle actions: snack · polish · wipe · music · selfie · scroll · game · wave
 * Also:         nap mode after a long idle, cursor high-five, skate-in entrance (state 'skate')
 * Built-in:     hover greeting, eyes follow the cursor, speech bubble after thumbs up.
 */

import { T } from './tokens';

export type PrudieState = 'idle' | 'wave' | 'skate' | 'search' | 'code' | 'thumbsup' | 'look';
export type IdleAction = 'snack' | 'polish' | 'wipe' | 'music' | 'selfie' | 'scroll' | 'game' | 'wave';
export const PRUDIE_STATES: PrudieState[] = ['idle', 'wave', 'skate', 'search', 'code', 'thumbsup', 'look'];
export const IDLE_ACTIONS: IdleAction[] = ['snack', 'polish', 'wipe', 'music', 'selfie', 'scroll', 'game', 'wave'];

export interface PrudieOptions {
  state?: PrudieState;
  /** Eyes follow the pointer while it is within `followRadius` px. Default true. */
  followPointer?: boolean;
  /** Radius in CSS px around Prudie inside which the eyes track the cursor. Default 460. */
  followRadius?: number;
  /** Seconds of rest between idle actions, as [min, max]. Default [2, 3]. null turns idle actions off. */
  idleEvery?: [number, number] | null;
  /** Seconds before the first idle action after Prudie becomes idle. Default 2. */
  idleFirstAfter?: number;
  /** Which idle actions may play. Default all of them. */
  idleActions?: IdleAction[];
  /** Seconds with no mouse movement, hover or state change before Prudie naps. Default 25. null = never. */
  napAfter?: number | null;
  /** Raise a palm when the cursor comes close; click Prudie for a high five. Default true. */
  highFive?: boolean;
  /** Greeting bubble text, shown after the skate-in lands and whenever Prudie is idle (doing nothing). Empty string turns it off. */
  greeting?: string;
  /** What Prudie says after a thumbs up, in order. Empty array = silent. */
  doneLines?: string[];
  /** Where the bubble sits. Default 'top'. */
  bubble?: 'top' | 'left' | 'right';
  /** wave and thumbsup play once, then return to idle. false = hold the pose. Default true. */
  oneShot?: boolean;
  /** Called when a one-shot action (wave, thumbsup) has finished. */
  onSettle?: (finished: PrudieState) => void;
}

export interface PrudieHandle {
  setState(state: PrudieState): void;
  wave(): void;
  /** Play one idle action now. */
  playIdle(action: IdleAction): void;
  /** Little hop. Also fired on tap. */
  poke(): void;
  /** Fall asleep now (sleep mask, zzz). Moving the mouse wakes Prudie up. */
  nap(): void;
  /** Wake up from a nap. */
  wake(): void;
  /** Viewport point (clientX/clientY) Prudie reads in 'look', e.g. the caret in the chat input. */
  setLookTarget(p: { x: number; y: number } | null): void;
  /** Show any text in the bubble for `ms` milliseconds (default 2500). */
  say(text: string, ms?: number): void;
  destroy(): void;
}

/* ───────────── palette ───────────── */
const SHELL = T.shell;
const SHELL_HI = T.shellHi;
const SHELL_LO = T.shellLo;
const SHELL_DEEP = T.shellDeep;
const SCREEN_A = T.screenTop;
const SCREEN_B = T.screenBot;
const EYE = T.eye;
const EYE_GLOW = T.eyeGlow;
const CYAN = T.hud;
const PINK = T.heart;
const BLUSH = T.blush;
const HOOD = T.hood;
const HOOD_HI = T.hoodHi;
const HOOD_LO = T.hoodLo;
const STRING = T.drawstring;
const GOLD = T.spark;
const GRAPH = T.glove;
const GRAPH_HI = T.gloveHi;
const GRAPH_LO = T.gloveLo;
const PAD = T.pad;
const CLOTH = T.cloth;
const CLOTH_LO = T.clothLo;

/* ───────────── geometry (design space 300 x 360, inside translate(0,22)) ───────────── */
const SH_L = { x: 100, y: 222 };
const SH_R = { x: 200, y: 222 };
const SH_L_PRONE = { x: 124, y: 318 };
const SH_R_PRONE = { x: 176, y: 318 };
const L1 = 30;
const L2 = 28;
const PIVOT = { x: 150, y: 206 };
const EYE_L = { x: 120, y: 124 };
const EYE_R = { x: 180, y: 124 };
const LENS_OFF = { x: -22, y: -50 };
const REST_L = { x: 86, y: 270 };
const REST_R = { x: 214, y: 270 };
const POCKET = { x: 192, y: 270 };
const PRONE_DROP = 90;
const MOUTH_Y = 154;

/* keyboard deck (seen from slightly above): far edge y 250, near edge (hinge) y 286 */
const KB_FAR = 250;
const KB_NEAR = 286;
const kbX = (y: number) => {
  const u = (y - KB_FAR) / (KB_NEAR - KB_FAR);
  return [lerp(100, 82, u), lerp(200, 218, u)];
};

const clamp = (v: number, a: number, b: number) => Math.min(b, Math.max(a, v));
const f1 = (n: number) => n.toFixed(1);
function lerp(a: number, b: number, t: number) {
  return a + (b - a) * t;
}
const rand = (a: number, b: number) => a + Math.random() * (b - a);
const hex = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
function mix(a: string, b: string, t: number) {
  const A = hex(a);
  const B = hex(b);
  return `rgb(${A.map((v, i) => Math.round(lerp(v, B[i], clamp(t, 0, 1)))).join(',')})`;
}
const angDiff = (a: number) => ((((a + 180) % 360) + 360) % 360) - 180;

let uid = 0;

/* ───────────── hands ─────────────
 * All poses are drawn for the RIGHT hand with the wrist at (0,0); the left hand is mirrored.
 * "up" poses (open, back, fist, thumb) have fingers toward -y, "down" poses (relax, type) toward +y.
 */
type Pose = 'relax' | 'open' | 'back' | 'fist' | 'thumb' | 'type' | 'peace';
const POSES: Pose[] = ['relax', 'open', 'back', 'fist', 'thumb', 'type', 'peace'];
const POSE_UP: Record<Pose, boolean> = { relax: false, open: true, back: true, fist: true, thumb: true, type: false, peace: true };

function cap(x1: number, y1: number, x2: number, y2: number, w: number) {
  return `<path d="M${x1} ${y1} L${x2} ${y2}" stroke="${GRAPH_LO}" stroke-width="${w + 2.2}" stroke-linecap="round"/>
    <path d="M${x1} ${y1} L${x2} ${y2}" stroke="${GRAPH}" stroke-width="${w}" stroke-linecap="round"/>
    <path d="M${f1(x1 - w * 0.18)} ${y1} L${f1(x2 - w * 0.18)} ${y2}" stroke="${GRAPH_HI}" stroke-width="${f1(w * 0.32)}" stroke-linecap="round"/>`;
}

function handMarkup(k: string) {
  const wrist = `<rect x="-9" y="-4" width="18" height="8" rx="4" fill="${SHELL_DEEP}"/><rect x="-9" y="-4" width="18" height="3" rx="1.5" fill="${EYE_GLOW}" opacity=".55"/>`;
  const openFingers = [
    [-8.5, -17, -11.5, -30],
    [-3, -18, -4.2, -35],
    [2.6, -18, 3.2, -34.5],
    [8, -17, 10.4, -29],
  ]
    .map(([a, b, c, d]) => cap(a, b, c, d, 6))
    .join('');
  const joints = [[-10.2, -24], [-3.7, -27], [2.9, -27], [9.4, -23.5]]
    .map(([x, y]) => `<path d="M${x - 2.4} ${y} L${x + 2.4} ${y}" stroke="${GRAPH_LO}" stroke-width="1.2" stroke-linecap="round"/>`)
    .join('');
  return `<g data-k="${k}">
    <g data-k="${k}open">
      ${openFingers}${joints}
      ${cap(-10, -8, -19, -17, 7)}
      <rect x="-12.5" y="-20" width="25" height="22" rx="9" fill="${GRAPH_LO}"/>
      <rect x="-11.5" y="-19.5" width="23" height="20" rx="8" fill="${GRAPH}"/>
      <rect x="-7.5" y="-15.5" width="15" height="11" rx="5" fill="${PAD}"/>
      <circle cx="0" cy="-10" r="5.5" fill="${EYE_GLOW}" opacity=".35"/>
      <circle cx="0" cy="-10" r="3" fill="${EYE}"/>
    </g>
    <g data-k="${k}back">
      ${openFingers}
      ${cap(-10, -8, -18, -16, 7)}
      <rect x="-12.5" y="-20" width="25" height="22" rx="9" fill="${GRAPH_LO}"/>
      <rect x="-11.5" y="-19.5" width="23" height="20" rx="8" fill="${GRAPH}"/>
      <g fill="${GRAPH_HI}"><circle cx="-8" cy="-16" r="2"/><circle cx="-2.6" cy="-17" r="2"/><circle cx="2.8" cy="-17" r="2"/><circle cx="8" cy="-16" r="2"/></g>
      <path d="M-7 -7 L7 -7" stroke="${EYE_GLOW}" stroke-width="1.6" stroke-linecap="round" opacity=".6"/>
    </g>
    <g data-k="${k}relax">
      <rect x="-11.5" y="-1" width="23" height="19" rx="8" fill="${GRAPH_LO}"/>
      <rect x="-10.5" y="-1" width="21" height="17.5" rx="7.5" fill="${GRAPH}"/>
      ${cap(-7, 15, -6, 22, 5.6)}${cap(-2, 16, -1.8, 24, 5.6)}${cap(3, 16, 3.2, 23.5, 5.6)}${cap(7.6, 15, 7.4, 21, 5.4)}
      ${cap(-10, 4, -14, 13, 6.4)}
      <path d="M-6 3 L6 3" stroke="${EYE_GLOW}" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>
    </g>
    <g data-k="${k}type">
      <rect x="-11.5" y="-1" width="23" height="16" rx="7" fill="${GRAPH_LO}"/>
      <rect x="-10.5" y="-1" width="21" height="14.5" rx="6.5" fill="${GRAPH}"/>
      <g data-k="${k}f0">${cap(-8, 11, -8.6, 20.5, 5.2)}</g>
      <g data-k="${k}f1">${cap(-2.8, 12, -2.9, 22.5, 5.2)}</g>
      <g data-k="${k}f2">${cap(2.6, 12, 2.8, 22.5, 5.2)}</g>
      <g data-k="${k}f3">${cap(7.8, 11, 8.4, 20, 5)}</g>
      ${cap(-10, 4, -12.5, 11, 6)}
      <path d="M-6 3 L6 3" stroke="${EYE_GLOW}" stroke-width="1.6" stroke-linecap="round" opacity=".55"/>
    </g>
    <g data-k="${k}fist">
      <rect x="-13" y="-17" width="26" height="21" rx="9" fill="${GRAPH_LO}"/>
      <rect x="-12" y="-16.5" width="24" height="19" rx="8" fill="${GRAPH}"/>
      <path d="M-11 -12 Q-8.5 -16 -6 -12 M-5.5 -12 Q-3 -16 -0.5 -12 M0 -12 Q2.5 -16 5 -12 M5.5 -12 Q8 -16 10.5 -12" stroke="${GRAPH_HI}" stroke-width="1.8" fill="none" stroke-linecap="round"/>
      <path d="M-6 -12 L-6 -6 M-0.5 -12 L-0.5 -6 M5 -12 L5 -6" stroke="${GRAPH_LO}" stroke-width="1.2" stroke-linecap="round"/>
      ${cap(-12, -3, 1, -6, 6.6)}
    </g>
    <g data-k="${k}thumb">
      ${cap(-7, -14, -7.5, -36, 10.5)}
      <rect x="-11" y="-38" width="7" height="6" rx="3" fill="${GRAPH_HI}"/>
      <rect x="-14" y="-18" width="28" height="24" rx="10" fill="${GRAPH_LO}"/>
      <rect x="-13" y="-17.5" width="26" height="22" rx="9" fill="${GRAPH}"/>
      ${cap(-1, -12, 10, -12, 6.4)}${cap(-1, -5.5, 11, -5.5, 6.4)}${cap(-1, 1, 10, 1, 6.2)}
      <path d="M-8 -8 L-8 2" stroke="${EYE_GLOW}" stroke-width="2" stroke-linecap="round" opacity=".7"/>
    </g>
    <g data-k="${k}peace">
      ${cap(-4, -16, -9, -35, 6.2)}${cap(2, -16, 6, -35, 6.2)}
      <rect x="-13" y="-18" width="26" height="22" rx="9" fill="${GRAPH_LO}"/>
      <rect x="-12" y="-17.5" width="24" height="20" rx="8" fill="${GRAPH}"/>
      <path d="M5 -13 Q8 -17 11 -13" stroke="${GRAPH_HI}" stroke-width="1.8" fill="none" stroke-linecap="round"/>
      ${cap(-12, -3, 2, -7, 6.6)}
      <rect x="-5" y="-12" width="10" height="3" rx="1.5" fill="${EYE_GLOW}" opacity=".7"/>
    </g>
    ${wrist}
  </g>`;
}

/* ───────────── markup ───────────── */
function pixelHeart(cx: number, cy: number) {
  const rows = ['.XX.XX.', 'XXXXXXX', 'XXXXXXX', '.XXXXX.', '..XXX..', '...X...'];
  const sz = 4.6;
  let out = '';
  rows.forEach((r, y) =>
    [...r].forEach((c, x) => {
      if (c === 'X') out += `<rect x="${f1(cx + (x - 3.5) * sz)}" y="${f1(cy + (y - 3) * sz)}" width="${sz - 0.6}" height="${sz - 0.6}" rx="1"/>`;
    }),
  );
  return out;
}

function eye(k: string) {
  return `<g data-k="${k}">
      <rect x="-14" y="-18" width="28" height="36" rx="12" fill="${EYE_GLOW}" opacity=".75" filter="url(#g6{ID})"/>
      <rect x="-11" y="-15" width="22" height="30" rx="10" fill="${EYE}"/>
      <rect x="-7" y="-11" width="7" height="9" rx="3.5" fill="#fff" opacity=".9"/>
    </g>`;
}

function note(k: string, double: boolean) {
  return double
    ? `<g data-k="${k}"><path d="M-4 6 L-4 -12 L8 -15 L8 3" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linejoin="round"/><ellipse cx="-7" cy="6" rx="4.4" ry="3.4" fill="currentColor"/><ellipse cx="5" cy="3" rx="4.4" ry="3.4" fill="currentColor"/></g>`
    : `<g data-k="${k}"><path d="M2 5 L2 -12 Q7 -10 9 -5" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round"/><ellipse cx="-1" cy="5" rx="4.6" ry="3.6" fill="currentColor"/></g>`;
}

function build(id: number) {
  const star = (k: string) =>
    `<g data-k="${k}"><path d="M0 -9 Q1.4 -1.4 9 0 Q1.4 1.4 0 9 Q-1.4 1.4 -9 0 Q-1.4 -1.4 0 -9Z" fill="${GOLD}" stroke="#fff" stroke-width="1.4" stroke-linejoin="round"/></g>`;

  const torso =
    'M106 198 L194 198 Q207 198 208 212 L212 268 Q214 292 192 294 L108 294 Q86 292 88 268 L92 212 Q93 198 106 198Z';
  const hoodTorso =
    'M98 194 L202 194 Q220 196 222 216 L226 272 Q228 300 200 302 L100 302 Q72 300 74 272 L78 216 Q80 196 98 194Z';
  const hoodOuter = 'M150 20 C 220 20 266 62 266 128 C 266 190 236 218 150 220 C 64 218 34 190 34 128 C 34 62 80 20 150 20 Z';
  const hoodHole = 'M114 66 L186 66 Q232 66 232 110 L232 146 Q232 190 186 190 L114 190 Q68 190 68 146 L68 110 Q68 66 114 66 Z';

  let keys = '';
  [256, 264.5, 273].forEach((y, r) => {
    const [xl, xr] = kbX(y);
    const n = 12;
    const gap = 1.6;
    const w = (xr - xl - 8 - gap * (n - 1)) / n;
    for (let i = 0; i < n; i++) {
      keys += `<rect data-key="${r * 12 + i}" x="${f1(xl + 4 + i * (w + gap))}" y="${y}" width="${f1(w)}" height="6" rx="1.6" fill="${GRAPH}"/>`;
    }
  });
  {
    const y = 281.5;
    const [xl, xr] = kbX(y);
    const mid = (xl + xr) / 2;
    keys += `<rect data-key="36" x="${f1(mid - 30)}" y="${y}" width="60" height="5.5" rx="1.6" fill="${GRAPH}"/>`;
  }

  const napkin = `
        <path d="M-17 -6 Q-15 -26 2 -28 Q17 -26 16 -8 Q17 7 0 7 Q-16 9 -17 -6Z" fill="${CLOTH}"/>
        <path d="M-10 -19 Q-2 -13 -6 -2 M5 -21 Q9 -13 6 -2" stroke="${CLOTH_LO}" stroke-width="2" fill="none" stroke-linecap="round"/>
        <path d="M-12 -18 Q-6 -24 2 -24" stroke="#fff" stroke-width="2.2" fill="none" stroke-linecap="round" opacity=".55"/>`;

  return `
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 360" width="100%" height="100%"
     role="img" aria-label="Prudie, the Prudentia mascot" style="display:block;overflow:visible;pointer-events:none">
  <defs>
    <radialGradient id="sh{ID}" cx=".32" cy=".22" r=".95">
      <stop offset="0" stop-color="${SHELL_HI}"/><stop offset=".45" stop-color="${SHELL}"/><stop offset="1" stop-color="${SHELL_LO}"/>
    </radialGradient>
    <radialGradient id="bd{ID}" cx=".36" cy=".15" r=".95">
      <stop offset="0" stop-color="${SHELL_HI}"/><stop offset=".5" stop-color="${SHELL}"/><stop offset="1" stop-color="${SHELL_LO}"/>
    </radialGradient>
    <linearGradient id="sc{ID}" x1="0" y1="0" x2=".35" y2="1">
      <stop offset="0" stop-color="${SCREEN_A}"/><stop offset="1" stop-color="${SCREEN_B}"/>
    </linearGradient>
    <radialGradient id="hd{ID}" cx=".35" cy=".2" r=".95">
      <stop offset="0" stop-color="${HOOD_HI}"/><stop offset=".55" stop-color="${HOOD}"/><stop offset="1" stop-color="${HOOD_LO}"/>
    </radialGradient>
    <linearGradient id="slv{ID}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#F4F5FB"/><stop offset="1" stop-color="#B0B3C8"/>
    </linearGradient>
    <linearGradient id="deck{ID}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#CDCFDF"/><stop offset="1" stop-color="#E4E5F0"/>
    </linearGradient>
    <linearGradient id="ft{ID}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="${SHELL}"/><stop offset="1" stop-color="${SHELL_DEEP}"/>
    </linearGradient>
    <linearGradient id="skate{ID}" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="${PINK}"/><stop offset=".5" stop-color="${SHELL}"/><stop offset="1" stop-color="${CYAN}"/>
    </linearGradient>
    <linearGradient id="bun{ID}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#F6B861"/><stop offset="1" stop-color="#D9893A"/>
    </linearGradient>
    <linearGradient id="irid{ID}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="${CYAN}"/><stop offset=".55" stop-color="${EYE_GLOW}"/><stop offset="1" stop-color="${PINK}"/>
    </linearGradient>
    <linearGradient id="ring{ID}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset=".35" stop-color="#E4E5F0"/><stop offset=".7" stop-color="#9498B2"/><stop offset="1" stop-color="#D6D8E6"/>
    </linearGradient>
    <linearGradient id="pearl{ID}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#FFFFFF"/><stop offset=".5" stop-color="#DADCEA"/><stop offset="1" stop-color="#9BA0BA"/>
    </linearGradient>
    <radialGradient id="glass{ID}" r=".5">
      <stop offset=".55" stop-color="${CYAN}" stop-opacity=".04"/><stop offset="1" stop-color="${CYAN}" stop-opacity=".32"/>
    </radialGradient>
    <radialGradient id="cg{ID}"><stop offset="0" stop-color="#8CF0C8" stop-opacity=".55"/><stop offset="1" stop-color="#8CF0C8" stop-opacity="0"/></radialGradient>
    <filter id="g6{ID}" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="5"/></filter>
    <filter id="g2{ID}" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="1.6"/></filter>
    <filter id="b8{ID}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter>
    <filter id="b3{ID}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="3"/></filter>
    <clipPath id="hc{ID}"><rect x="56" y="50" width="188" height="156" rx="64"/></clipPath>
    <clipPath id="scc{ID}"><rect x="74" y="70" width="152" height="116" rx="44"/></clipPath>
    <clipPath id="tc{ID}"><path d="${torso}"/></clipPath>
    <clipPath id="htc{ID}"><path d="${hoodTorso}"/></clipPath>
    <clipPath id="lensc{ID}"><circle r="24"/></clipPath>
    <mask id="bite{ID}" maskUnits="userSpaceOnUse" x="-40" y="-40" width="80" height="80">
      <rect x="-40" y="-40" width="80" height="80" fill="#fff"/>
      <g fill="#000">
        <circle data-k="bite0" cx="-17" cy="-11" r="0"/><circle cx="-12" cy="-17" r="0" data-k="bite0b"/>
        <circle data-k="bite1" cx="-20" cy="0" r="0"/><circle cx="-17" cy="-5" r="0" data-k="bite1b"/>
      </g>
    </mask>
  </defs>

  <g transform="translate(0 22)">
    <ellipse data-k="shadow" cx="150" cy="314" rx="64" ry="9" fill="#15141B" opacity=".16"/>

    <g data-k="char">
      <!-- lying-down pose: back, one leg on each side kicking in turn, elbows on the floor -->
      <g data-k="prone" opacity="0">
        <ellipse cx="150" cy="160" rx="72" ry="34" fill="url(#bd{ID})"/>
        <ellipse cx="128" cy="140" rx="28" ry="9" fill="#fff" opacity=".2"/>
        <g data-k="legPL"><g data-k="legPLshin">
          <path d="M112 166 L106 140" stroke="${SHELL_LO}" stroke-width="24" stroke-linecap="round"/>
          <path d="M112 166 L106 140" stroke="${SHELL}" stroke-width="19" stroke-linecap="round"/>
          <g transform="translate(102 116) scale(1.3 1.3)">
            <path d="M14 10 L-24 10 Q-30 10 -30 3 Q-30 -6 -20 -8 L-6 -10 Q2 -22 12 -20 Q18 -18 18 -6 L18 6 Q18 10 14 10Z" fill="${SHELL_DEEP}"/>
            <path d="M12 3 L-22 3 Q-27 3 -27 -1 Q-27 -6 -19 -7 L-6 -9 Q1 -19 10 -17 Q15 -16 15 -6 L15 0 Q15 3 12 3Z" fill="${SHELL}"/>
            <path d="M-31 6 L17 6" stroke="#F0F1F8" stroke-width="7" stroke-linecap="round"/>
            <path d="M-12 -6 L4 -14" stroke="${EYE_GLOW}" stroke-width="3.4" stroke-linecap="round"/>
            <ellipse cx="6" cy="-14" rx="5" ry="2.4" fill="#fff" opacity=".35"/>
          </g>
        </g></g>
        <g data-k="legPR"><g data-k="legPRshin">
          <path d="M188 166 L194 140" stroke="${SHELL_LO}" stroke-width="24" stroke-linecap="round"/>
          <path d="M188 166 L194 140" stroke="${SHELL}" stroke-width="19" stroke-linecap="round"/>
          <g transform="translate(198 116) scale(-1.3 1.3)">
            <path d="M14 10 L-24 10 Q-30 10 -30 3 Q-30 -6 -20 -8 L-6 -10 Q2 -22 12 -20 Q18 -18 18 -6 L18 6 Q18 10 14 10Z" fill="${SHELL_DEEP}"/>
            <path d="M12 3 L-22 3 Q-27 3 -27 -1 Q-27 -6 -19 -7 L-6 -9 Q1 -19 10 -17 Q15 -16 15 -6 L15 0 Q15 3 12 3Z" fill="${SHELL}"/>
            <path d="M-31 6 L17 6" stroke="#F0F1F8" stroke-width="7" stroke-linecap="round"/>
            <path d="M-12 -6 L4 -14" stroke="${EYE_GLOW}" stroke-width="3.4" stroke-linecap="round"/>
            <ellipse cx="6" cy="-14" rx="5" ry="2.4" fill="#fff" opacity=".35"/>
          </g>
        </g></g>
        <ellipse cx="80" cy="306" rx="18" ry="11" fill="${SHELL_LO}"/>
        <ellipse cx="220" cy="306" rx="18" ry="11" fill="${SHELL_LO}"/>
        <ellipse cx="78" cy="303" rx="13" ry="7" fill="${SHELL}"/>
        <ellipse cx="218" cy="303" rx="13" ry="7" fill="${SHELL}"/>
      </g>

      <g data-k="stand">
        <g data-k="legL">
          <rect x="113" y="276" width="30" height="32" rx="13" fill="url(#ft{ID})"/>
          <ellipse cx="128" cy="306" rx="19" ry="8" fill="${SHELL_DEEP}"/>
          <ellipse cx="125" cy="303" rx="14" ry="5" fill="${SHELL_LO}"/>
        </g>
        <g data-k="legR">
          <rect x="157" y="276" width="30" height="32" rx="13" fill="url(#ft{ID})"/>
          <ellipse cx="172" cy="306" rx="19" ry="8" fill="${SHELL_DEEP}"/>
          <ellipse cx="169" cy="303" rx="14" ry="5" fill="${SHELL_LO}"/>
        </g>

        <g data-k="torso">
          <path d="${torso}" fill="url(#bd{ID})"/>
          <g clip-path="url(#tc{ID})">
            <ellipse cx="150" cy="200" rx="70" ry="18" fill="${SHELL_DEEP}" opacity=".55" filter="url(#b8{ID})"/>
            <ellipse cx="122" cy="236" rx="16" ry="30" fill="#fff" opacity=".22" filter="url(#b8{ID})"/>
            <ellipse cx="176" cy="296" rx="60" ry="16" fill="${SHELL_DEEP}" opacity=".35" filter="url(#b8{ID})"/>
            <!-- jeans-style front pocket on the right hip: napkin peeking out of the curved opening -->
            <path data-k="pocketCloth" d="M174 266 Q178 254 186 262 Q190 252 198 264 Z" fill="${CLOTH}"/>
            <path d="M170 262 Q176 282 214 288 L214 262 Z" fill="${SHELL_LO}"/>
            <path d="M170 262 Q176 282 214 288" fill="none" stroke="${SHELL_DEEP}" stroke-width="2.4" stroke-linecap="round"/>
            <path d="M175 263 Q181 279 214 284" fill="none" stroke="${SHELL_HI}" stroke-width="1.4" stroke-dasharray="2.5 2.5" opacity=".75"/>
          </g>
          <rect x="118" y="234" width="30" height="11" rx="5.5" fill="${SCREEN_B}" opacity=".55"/>
          <circle data-k="led" cx="125" cy="239.5" r="2.4" fill="${EYE_GLOW}"/>
          <circle cx="133" cy="239.5" r="2.4" fill="${EYE_GLOW}" opacity=".5"/>
          <circle cx="141" cy="239.5" r="2.4" fill="${EYE_GLOW}" opacity=".25"/>
        </g>

        <g data-k="hoodTorso" opacity="0">
          <path d="${hoodTorso}" fill="url(#hd{ID})"/>
          <g clip-path="url(#htc{ID})">
            <ellipse cx="150" cy="198" rx="76" ry="18" fill="${HOOD_LO}" opacity=".8" filter="url(#b8{ID})"/>
            <ellipse cx="114" cy="236" rx="16" ry="36" fill="#fff" opacity=".2" filter="url(#b8{ID})"/>
            <rect x="70" y="286" width="160" height="20" fill="${HOOD_LO}"/>
            <path d="M84 288 V304M94 288 V304M104 288 V304M114 288 V304M124 288 V304M134 288 V304M144 288 V304M154 288 V304M164 288 V304M174 288 V304M184 288 V304M194 288 V304M204 288 V304M214 288 V304" stroke="${HOOD}" stroke-width="1.6" opacity=".7"/>
          </g>
          <path d="M112 254 L188 254 Q196 254 198 262 L202 282 Q202 286 198 286 L102 286 Q98 286 98 282 L102 262 Q104 254 112 254Z" fill="${HOOD_LO}" opacity=".55"/>
          <path d="M136 210 C 134 226 132 238 131 252" fill="none" stroke="${STRING}" stroke-width="3.4" stroke-linecap="round"/>
          <path d="M164 210 C 166 226 168 238 169 252" fill="none" stroke="${STRING}" stroke-width="3.4" stroke-linecap="round"/>
          <rect x="128" y="250" width="6" height="9" rx="2" fill="#E4E5F0"/>
          <rect x="166" y="250" width="6" height="9" rx="2" fill="#E4E5F0"/>
        </g>
      </g>

      <!-- skateboard (skate-in entrance) -->
      <g data-k="board" opacity="0">
        <ellipse cx="150" cy="336" rx="96" ry="6" fill="#15141B" opacity=".18"/>
        <path d="M54 304 Q58 314 72 314 L228 314 Q242 314 246 304 Q250 320 232 322 L68 322 Q50 320 54 304Z" fill="url(#skate{ID})"/>
        <path d="M64 315 L236 315" stroke="${GRAPH}" stroke-width="3" stroke-linecap="round"/>
        <path d="M70 320 L230 320" stroke="#fff" stroke-width="1.4" opacity=".5"/>
        <rect x="90" y="322" width="20" height="5" rx="2" fill="#B0B3C8"/>
        <rect x="190" y="322" width="20" height="5" rx="2" fill="#B0B3C8"/>
        <g data-k="wheel0" transform="translate(100 330)"><circle r="7.5" fill="${CYAN}"/><circle r="3" fill="#fff"/><path d="M-6 0 L6 0" stroke="#2F9F78" stroke-width="2"/></g>
        <g data-k="wheel1" transform="translate(200 330)"><circle r="7.5" fill="${CYAN}"/><circle r="3" fill="#fff"/><path d="M-6 0 L6 0" stroke="#2F9F78" stroke-width="2"/></g>
      </g>
      <g data-k="dust" opacity="0" fill="#D6D8E6"><circle data-k="d0" r="7"/><circle data-k="d1" r="5"/><circle data-k="d2" r="6"/></g>

      <!-- head -->
      <g data-k="head">
        <rect x="42" y="110" width="18" height="40" rx="8" fill="${SHELL_LO}"/>
        <rect x="240" y="110" width="18" height="40" rx="8" fill="${SHELL_LO}"/>
        <rect x="44" y="114" width="10" height="32" rx="5" fill="${SHELL}"/>
        <rect x="246" y="114" width="10" height="32" rx="5" fill="${SHELL}"/>
        <rect x="47.5" y="122" width="3" height="16" rx="1.5" fill="${T.earLed}" opacity=".9"/>
        <rect x="249.5" y="122" width="3" height="16" rx="1.5" fill="${T.earLed}" opacity=".9"/>
        <rect x="56" y="50" width="188" height="156" rx="64" fill="url(#sh{ID})"/>
        <g clip-path="url(#hc{ID})">
          <ellipse cx="104" cy="58" rx="56" ry="18" fill="#fff" opacity=".45" filter="url(#b8{ID})"/>
          <ellipse cx="168" cy="210" rx="110" ry="26" fill="${SHELL_DEEP}" opacity=".5" filter="url(#b8{ID})"/>
        </g>

        <rect x="70" y="66" width="160" height="124" rx="48" fill="${SHELL_DEEP}" opacity=".55"/>
        <rect x="74" y="70" width="152" height="116" rx="44" fill="url(#sc{ID})"/>
        <g clip-path="url(#scc{ID})">
          <ellipse data-k="codeGlow" cx="150" cy="200" rx="110" ry="60" fill="url(#cg{ID})" opacity="0"/>
          <g data-k="codeLines" opacity="0"></g>
          <g data-k="face">
            <ellipse data-k="blushL" cx="98" cy="152" rx="13" ry="7" fill="${BLUSH}" opacity=".35" filter="url(#b3{ID})"/>
            <ellipse data-k="blushR" cx="202" cy="152" rx="13" ry="7" fill="${BLUSH}" opacity=".35" filter="url(#b3{ID})"/>
            ${eye('eyeL')}
            ${eye('eyeR')}
            <g data-k="happyL" opacity="0"><path d="M-13 6 Q0 -12 13 6" fill="none" stroke="${EYE_GLOW}" stroke-width="9" stroke-linecap="round" opacity=".6" filter="url(#b3{ID})"/><path d="M-13 6 Q0 -12 13 6" fill="none" stroke="${EYE}" stroke-width="5.5" stroke-linecap="round"/></g>
            <g data-k="happyR" opacity="0"><path d="M-13 6 Q0 -12 13 6" fill="none" stroke="${EYE_GLOW}" stroke-width="9" stroke-linecap="round" opacity=".6" filter="url(#b3{ID})"/><path d="M-13 6 Q0 -12 13 6" fill="none" stroke="${EYE}" stroke-width="5.5" stroke-linecap="round"/></g>
            <g data-k="shutL" opacity="0"><path d="M-12 -6 L2 0 L-12 6" fill="none" stroke="${EYE}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>
            <g data-k="shutR" opacity="0"><path d="M12 -6 L-2 0 L12 6" fill="none" stroke="${EYE}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/></g>
            <circle data-k="whistle" cx="150" cy="157" r="4" fill="none" stroke="${EYE}" stroke-width="2.6" opacity="0"/>
            <g data-k="xL" opacity="0"><path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${EYE_GLOW}" stroke-width="9" stroke-linecap="round" opacity=".55" filter="url(#b3{ID})"/><path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${EYE}" stroke-width="5" stroke-linecap="round"/></g>
            <g data-k="xR" opacity="0"><path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${EYE_GLOW}" stroke-width="9" stroke-linecap="round" opacity=".55" filter="url(#b3{ID})"/><path d="M-10 -10 L10 10 M10 -10 L-10 10" stroke="${EYE}" stroke-width="5" stroke-linecap="round"/></g>
            <g data-k="heart" opacity="0" fill="${PINK}">
              <g opacity=".5" filter="url(#b3{ID})">${pixelHeart(EYE_L.x, EYE_L.y)}${pixelHeart(EYE_R.x, EYE_R.y)}</g>
              ${pixelHeart(EYE_L.x, EYE_L.y)}${pixelHeart(EYE_R.x, EYE_R.y)}
            </g>
            <path data-k="mouth" fill="${EYE}" stroke="${EYE}" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>
          </g>
          <path d="M84 98 Q92 76 120 72" fill="none" stroke="#fff" stroke-width="5" stroke-linecap="round" opacity=".16"/>
          <path data-k="shine" d="M-30 186 L10 70 L34 70 L-6 186Z" fill="#fff" opacity="0"/>
        </g>
        <rect x="74" y="70" width="152" height="116" rx="44" fill="none" stroke="${SHELL_HI}" stroke-opacity=".34" stroke-width="2"/>

        <!-- smart glasses: graphite frame, iridescent lenses, status light -->
        <g data-k="glasses" opacity="0">
          <path d="M93 118 L56 113" stroke="url(#pearl{ID})" stroke-width="5" stroke-linecap="round"/>
          <path d="M207 118 L244 113" stroke="url(#pearl{ID})" stroke-width="5" stroke-linecap="round"/>
          <rect x="${EYE_L.x - 26}" y="${EYE_L.y - 20}" width="52" height="40" rx="15" fill="url(#irid{ID})" fill-opacity=".3"/>
          <rect x="${EYE_R.x - 26}" y="${EYE_R.y - 20}" width="52" height="40" rx="15" fill="url(#irid{ID})" fill-opacity=".3"/>
          <rect x="${EYE_L.x - 26}" y="${EYE_L.y - 20}" width="52" height="40" rx="15" fill="none" stroke="${CYAN}" stroke-width="7" opacity=".25" filter="url(#g2{ID})"/>
          <rect x="${EYE_R.x - 26}" y="${EYE_R.y - 20}" width="52" height="40" rx="15" fill="none" stroke="${CYAN}" stroke-width="7" opacity=".25" filter="url(#g2{ID})"/>
          <rect x="${EYE_L.x - 26}" y="${EYE_L.y - 20}" width="52" height="40" rx="15" fill="none" stroke="url(#pearl{ID})" stroke-width="4.5"/>
          <rect x="${EYE_R.x - 26}" y="${EYE_R.y - 20}" width="52" height="40" rx="15" fill="none" stroke="url(#pearl{ID})" stroke-width="4.5"/>
          <path d="M${EYE_L.x - 14} ${EYE_L.y + 20} L${EYE_L.x + 14} ${EYE_L.y + 20}" stroke="${CYAN}" stroke-width="1.6" stroke-linecap="round" opacity=".9"/>
          <path d="M${EYE_R.x - 14} ${EYE_R.y + 20} L${EYE_R.x + 14} ${EYE_R.y + 20}" stroke="${CYAN}" stroke-width="1.6" stroke-linecap="round" opacity=".9"/>
          <path d="M145 116 Q150 110 155 116" fill="none" stroke="url(#pearl{ID})" stroke-width="5" stroke-linecap="round"/>
          <path d="M${EYE_L.x - 18} ${EYE_L.y + 6} L${EYE_L.x - 6} ${EYE_L.y - 12}" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".4"/>
          <path d="M${EYE_R.x - 18} ${EYE_R.y + 6} L${EYE_R.x - 6} ${EYE_R.y - 12}" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".4"/>
          <circle cx="${EYE_R.x + 22}" cy="${EYE_R.y - 16}" r="5" fill="${CYAN}" opacity=".35" filter="url(#g2{ID})"/>
          <circle data-k="glassLed" cx="${EYE_R.x + 22}" cy="${EYE_R.y - 16}" r="2.4" fill="${CYAN}"/>
        </g>

        <g data-k="mask" opacity="0">
          <path d="M52 124 L82 122 M218 122 L248 124" stroke="#2C3A6E" stroke-width="7" stroke-linecap="round"/>
          <rect x="78" y="96" width="144" height="54" rx="26" fill="#7482C0"/>
          <rect x="80" y="97" width="140" height="50" rx="24" fill="#9AA7DD"/>
          <rect x="88" y="100" width="124" height="18" rx="9" fill="#fff" opacity=".22"/>
          <path d="M101 124 Q120 136 139 124 M161 124 Q180 136 199 124" fill="none" stroke="#1C2548" stroke-width="3.6" stroke-linecap="round"/>
          <path d="M106 130 L103 135 M120 133 L120 138 M134 130 L137 135 M166 130 L163 135 M180 133 L180 138 M194 130 L197 135" stroke="#1C2548" stroke-width="2.4" stroke-linecap="round"/>
          <circle cx="150" cy="108" r="3.4" fill="${GOLD}"/>
        </g>
        <g data-k="hood" opacity="0">
          <path d="${hoodOuter} ${hoodHole}" fill-rule="evenodd" fill="url(#hd{ID})"/>
          <path d="${hoodHole}" fill="none" stroke="${HOOD_LO}" stroke-width="5"/>
          <path d="M60 150 C 50 96 84 44 150 36" fill="none" stroke="#fff" stroke-width="3" stroke-linecap="round" opacity=".22"/>
          <path d="M150 22 C 154 40 152 56 150 66" fill="none" stroke="${HOOD_LO}" stroke-width="2.5" opacity=".5"/>
        </g>
        <g data-k="phones" opacity="0">
          <path d="M40 138 C 34 52 92 8 150 8 C 208 8 266 52 260 138" fill="none" stroke="${GRAPH}" stroke-width="11" stroke-linecap="round"/>
          <path d="M46 116 C 46 60 96 18 150 16" fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" opacity=".2"/>
          <g transform="translate(36 148)"><rect x="-15" y="-30" width="30" height="60" rx="13" fill="${GRAPH}"/><rect x="-6" y="-20" width="5" height="40" rx="2.5" fill="${EYE_GLOW}"/></g>
          <g transform="translate(264 148)"><rect x="-15" y="-30" width="30" height="60" rx="13" fill="${GRAPH}"/><rect x="1" y="-20" width="5" height="40" rx="2.5" fill="${EYE_GLOW}"/></g>
        </g>
      </g>

      <!-- laptop deck with keyboard (behind the hands) -->
      <g data-k="deck" opacity="0">
        <ellipse cx="150" cy="330" rx="122" ry="7" fill="#15141B" opacity=".16"/>
        <rect x="24" y="310" width="252" height="18" rx="9" fill="#D0D2E2"/>
        <rect x="24" y="310" width="252" height="8" rx="4" fill="#F0F1F8"/>
        <path d="M100 ${KB_FAR} L200 ${KB_FAR} L218 ${KB_NEAR} L82 ${KB_NEAR} Z" fill="url(#deck{ID})" stroke="#A5A8BE" stroke-width="1.4" stroke-linejoin="round"/>
        <g data-k="keys">${keys}</g>
      </g>

      <!-- props held behind the fingers -->
      <g data-k="juice" opacity="0">
        <path data-k="straw" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round"/>
        <path data-k="strawStripe" fill="none" stroke="#FF6B8B" stroke-width="3.4" stroke-dasharray="3 4"/>
        <rect x="-11" y="-32" width="22" height="32" rx="3.5" fill="#FF9B3D"/>
        <rect x="-11" y="-32" width="7" height="32" rx="3" fill="#FFB86B"/>
        <rect x="-11" y="-32" width="22" height="5" rx="2" fill="#F07D1E"/>
        <circle cx="1" cy="-15" r="6" fill="#FFE07A"/><path d="M1 -19.5 Q4.5 -23 7 -20.5" stroke="#4FA34A" stroke-width="2.2" fill="none" stroke-linecap="round"/>
      </g>

      <!-- arms -->
      <path data-k="armLb" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      <path data-k="armLm" fill="none" stroke-linecap="round" stroke-linejoin="round" transform="translate(-1 -1.5)"/>
      <path data-k="armLh" fill="none" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" transform="translate(-4 -4.5)"/>
      <circle data-k="elbowL" r="6" fill="${SHELL_DEEP}"/>

      <path data-k="armRb" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
      <path data-k="armRm" fill="none" stroke-linecap="round" stroke-linejoin="round" transform="translate(-1 -1.5)"/>
      <path data-k="armRh" fill="none" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round" transform="translate(-4 -4.5)"/>
      <circle data-k="elbowR" r="6" fill="${SHELL_DEEP}"/>

      <!-- scanning lens: graphite ring, cyan HUD, LED handle -->
      <g data-k="lens" opacity="0">
        <path d="M0 0 L ${f1(LENS_OFF.x * 0.52)} ${f1(LENS_OFF.y * 0.52)}" stroke="#8A8EAA" stroke-width="12" stroke-linecap="round"/>
        <path d="M0 0 L ${f1(LENS_OFF.x * 0.52)} ${f1(LENS_OFF.y * 0.52)}" stroke="url(#pearl{ID})" stroke-width="9" stroke-linecap="round"/>
        <path d="M${f1(LENS_OFF.x * 0.1)} ${f1(LENS_OFF.y * 0.1)} L ${f1(LENS_OFF.x * 0.42)} ${f1(LENS_OFF.y * 0.42)}" stroke="${EYE_GLOW}" stroke-width="2.4" stroke-linecap="round"/>
        <g transform="translate(${LENS_OFF.x} ${LENS_OFF.y})">
          <circle r="25" fill="url(#glass{ID})"/>
          <circle data-k="lensfog" r="24" fill="#fff" opacity="0"/>
          <g clip-path="url(#lensc{ID})">
            <path data-k="scan" d="M-30 0 L30 0" stroke="${CYAN}" stroke-width="2" opacity=".55"/>
          </g>
          <circle r="25" fill="none" stroke="${CYAN}" stroke-width="1.6" opacity=".9"/>
          <circle r="25" fill="none" stroke="${CYAN}" stroke-width="4" opacity=".35" filter="url(#g2{ID})"/>
          <circle r="30" fill="none" stroke="#8A8EAA" stroke-width="10.5"/>
          <circle r="30" fill="none" stroke="url(#ring{ID})" stroke-width="8"/>
          <circle r="34" fill="none" stroke="#fff" stroke-width="1" opacity=".35"/>
          <g data-k="hud" stroke="${CYAN}" stroke-width="2" stroke-linecap="round" opacity=".85">
            <path d="M0 -21 L0 -17 M21 0 L17 0 M0 21 L0 17 M-21 0 L-17 0"/>
            <path d="M-14 -14 A20 20 0 0 1 14 -14" fill="none" stroke-width="2.4"/>
          </g>
          <path d="M-16 -12 Q-11 -19 -3 -21" fill="none" stroke="#fff" stroke-width="3.4" stroke-linecap="round" opacity=".85"/>
          <circle cx="24" cy="-20" r="2.6" fill="${CYAN}"/>
        </g>
      </g>
      <g data-k="burger" opacity="0">
        <g mask="url(#bite{ID})">
          <path d="M-21 4 Q-21 14 0 14 Q21 14 21 4 Z" fill="url(#bun{ID})"/>
          <rect x="-22" y="-3" width="44" height="8" rx="4" fill="#7A3E22"/>
          <path d="M-22 -4 L22 -4 L17 3 L8 -2 L0 4 L-8 -2 L-17 3 Z" fill="#FFD447"/>
          <path d="M-23 -6 Q-17 -1 -11 -6 Q-5 -1 1 -6 Q7 -1 13 -6 Q19 -2 23 -6 L23 -4 L-23 -4 Z" fill="#6CC24A"/>
          <path d="M-21 -6 Q-21 -26 0 -26 Q21 -26 21 -6 Z" fill="url(#bun{ID})"/>
          <g fill="#FFF3D6"><ellipse cx="-8" cy="-17" rx="1.8" ry="1"/><ellipse cx="2" cy="-20" rx="1.8" ry="1"/><ellipse cx="10" cy="-14" rx="1.8" ry="1"/><ellipse cx="-2" cy="-12" rx="1.8" ry="1"/></g>
        </g>
      </g>
      <g data-k="cloth" opacity="0">${napkin}</g>
      <g data-k="phone" opacity="0">
        <rect x="-13" y="-48" width="26" height="44" rx="7" fill="${GRAPH_LO}"/>
        <rect x="-12" y="-47" width="24" height="42" rx="6.5" fill="${GRAPH}"/>
        <rect x="-9" y="-44" width="11" height="14" rx="4.5" fill="${GRAPH_LO}"/>
        <circle cx="-5.5" cy="-40.5" r="2.6" fill="${CYAN}"/><circle cx="-1.5" cy="-34" r="2.6" fill="${EYE_GLOW}"/>
        <rect x="-4.5" y="-24" width="9" height="9" rx="3" fill="${SHELL}"/>
        <path d="M-10 -45 L-10 -8" stroke="${GRAPH_HI}" stroke-width="1.6" stroke-linecap="round"/>
      </g>
      <g data-k="console" opacity="0">
        <rect x="-44" y="-22" width="88" height="44" rx="16" fill="#7482C0"/>
        <rect x="-43" y="-21" width="86" height="41" rx="15" fill="#BCC5EA"/>
        <rect x="-38" y="-19" width="76" height="12" rx="6" fill="#fff" opacity=".35"/>
        <rect x="-19" y="-15" width="38" height="28" rx="5" fill="${GRAPH_LO}"/>
        <rect data-k="cscreen" x="-16" y="-12" width="32" height="22" rx="3" fill="#1F3550"/>
        <g data-k="cpix">
          <rect data-k="cship" x="-3" y="4" width="6" height="4" rx="1" fill="${CYAN}"/>
          <rect data-k="cfoe" x="-3" y="-9" width="6" height="4" rx="1" fill="${PINK}"/>
          <rect data-k="cshot" x="-0.8" y="-2" width="1.6" height="4" fill="#fff"/>
        </g>
        <path d="M-35 0 L-25 0 M-30 -5 L-30 5" stroke="${GRAPH}" stroke-width="4.5" stroke-linecap="round"/>
        <circle cx="29" cy="-4" r="4.4" fill="${PINK}"/><circle cx="36" cy="4" r="4.4" fill="${CYAN}"/>
      </g>


      ${handMarkup('hL')}
      ${handMarkup('hR')}

      <!-- laptop lid back, nearest to us -->
      <g data-k="lid" opacity="0">
        <path d="M82 ${KB_NEAR} L218 ${KB_NEAR} L232 312 L68 312 Z" fill="url(#slv{ID})" stroke="url(#slv{ID})" stroke-width="5" stroke-linejoin="round"/>
        <path d="M82 ${KB_NEAR + 1} L218 ${KB_NEAR + 1}" stroke="#868899" stroke-width="3" stroke-linecap="round"/>
        <path d="M70 309 L230 309" stroke="#fff" stroke-width="1.6" opacity=".8"/>
        <g transform="translate(150 299)">
          <rect x="-11" y="-8" width="22" height="16" rx="6" fill="${SHELL}" opacity=".55" filter="url(#g6{ID})"/>
          <rect x="-8" y="-6" width="16" height="12" rx="4.5" fill="${SHELL}"/>
          <text y="4" text-anchor="middle" font-family="system-ui,-apple-system,'Segoe UI',sans-serif" font-weight="800" font-size="10" fill="#fff">P</text>
        </g>
      </g>

      <g data-k="glyphs" opacity="0" font-family="ui-monospace,SFMono-Regular,Menlo,monospace" font-weight="800" font-size="15" text-anchor="middle">
        <text data-k="gl0" fill="#fff" stroke="${SHELL_DEEP}" stroke-width="4" paint-order="stroke">&lt;/&gt;</text>
        <text data-k="gl1" fill="${GOLD}" stroke="${SHELL_DEEP}" stroke-width="4" paint-order="stroke">{ }</text>
        <text data-k="gl2" fill="${CYAN}" stroke="${SHELL_DEEP}" stroke-width="4" paint-order="stroke">01</text>
        <text data-k="gl3" fill="${EYE_GLOW}" stroke="${SHELL_DEEP}" stroke-width="4" paint-order="stroke">=&gt;</text>
      </g>
      <g data-k="notes" opacity="0">
        <g style="color:${EYE_GLOW}">${note('n0', false)}</g>
        <g style="color:${CYAN}">${note('n1', true)}</g>
        <g style="color:${PINK}">${note('n2', false)}</g>
        <g style="color:${GOLD}">${note('n3', true)}</g>
      </g>
      <g data-k="flash" opacity="0"><circle r="34" fill="#fff" opacity=".55" filter="url(#g6{ID})"/><circle r="11" fill="#fff"/>
        <path d="M0 -26 L0 -16 M0 16 L0 26 M-26 0 L-16 0 M16 0 L26 0 M-18 -18 L-12 -12 M12 12 L18 18 M18 -18 L12 -12 M-12 12 L-18 18" stroke="#fff" stroke-width="3.4" stroke-linecap="round"/></g>
      <g data-k="five" opacity="0">
        <circle data-k="fiveRing" r="20" fill="none" stroke="${CYAN}" stroke-width="3"/>
        <path d="M0 -30 L0 -20 M0 20 L0 30 M-30 0 L-20 0 M20 0 L30 0 M-21 -21 L-14 -14 M14 14 L21 21 M21 -21 L14 -14 M-14 14 L-21 21" stroke="${GOLD}" stroke-width="4" stroke-linecap="round"/>
      </g>
      <g data-k="zzz" opacity="0" font-family="system-ui,-apple-system,'Segoe UI',sans-serif" font-weight="900" fill="${EYE_GLOW}" stroke="${SHELL_DEEP}" stroke-width="3.4" paint-order="stroke">
        <text data-k="z0" font-size="16">Z</text><text data-k="z1" font-size="21">Z</text><text data-k="z2" font-size="27">Z</text>
      </g>
      <g data-k="puff" opacity="0"><circle r="7" fill="#fff"/><circle cx="8" cy="-3" r="6" fill="#fff"/><circle cx="4" cy="5" r="5" fill="#fff"/></g>
      <g data-k="sparks" opacity="0">${star('sp0')}${star('sp1')}${star('sp2')}${star('sp3')}</g>
    </g>
  </g>
</svg>`.replace(/\{ID\}/g, String(id));
}

/* ───────────── springs ───────────── */
interface Spring {
  v: number;
  vel: number;
  t: number;
  k: number;
  z: number;
}

const BASE = {
  tilt: 0, hx: 0, hy: 0, lean: 0, bodyY: 0, squash: 0, prone: 0,
  gx: 0, gy: 0,
  happy: 0, shut: 0, squint: 0, mw: 7, mc: 4, mo: 0, mouth: 0.75, blush: 0.35,
  lx: REST_L.x, ly: REST_L.y, rx: REST_R.x, ry: REST_R.y, wristL: 0, wristR: 0,
  hood: 0, phones: 0, laptop: 0, glasses: 0, lens: 0, sparkle: 0, glow: 0,
  burger: 0, juice: 0, cloth: 0, whistle: 0, phone: 0, pglow: 0, xd: 0, heart: 0, game: 0, mask: 0, nap: 0, board: 0, fog: 0, puff: 0, shine: 0, notes: 0, tap: 0,
};
type Key = keyof typeof BASE;
type Targets = Record<Key, number> & { poseL: Pose; poseR: Pose; lensHand: 'L' | 'R' };

const CFG: Partial<Record<Key, [number, number]>> = {
  gx: [300, 0.9], gy: [300, 0.9],
  lx: [210, 0.68], ly: [210, 0.68], rx: [210, 0.68], ry: [210, 0.68], wristL: [200, 0.7], wristR: [200, 0.7],
  mw: [260, 0.85], mc: [260, 0.85], mo: [320, 0.8], mouth: [140, 1], blush: [100, 1],
  happy: [130, 1], shut: [160, 1], squint: [150, 1],
  hood: [65, 0.55], phones: [90, 0.5], laptop: [70, 0.62], glasses: [110, 0.55], lens: [90, 0.7],
  sparkle: [90, 1], glow: [60, 1], burger: [140, 0.6], juice: [140, 0.6], cloth: [160, 0.7],
  phone: [150, 0.62], pglow: [60, 1], xd: [220, 1], heart: [220, 1], game: [140, 0.62], mask: [80, 0.55], nap: [50, 1], board: [120, 1],
  fog: [40, 1], puff: [60, 1], shine: [30, 1], notes: [60, 1], tap: [400, 0.5],
  tilt: [130, 0.55], hx: [120, 0.8], hy: [120, 0.8], lean: [110, 0.6], prone: [55, 0.78],
  squash: [280, 0.38], bodyY: [210, 0.46],
};

const ONE_SHOT: Partial<Record<PrudieState, number>> = { wave: 2.9, thumbsup: 3.8, skate: 4.0 };
const IDLE_LEN: Record<Exclude<IdleAction, 'wave'>, number> = { snack: 6.6, polish: 5.6, wipe: 5.0, music: 7.5, selfie: 5.8, scroll: 6.6, game: 6.8 };

/* ───────────── IK ───────────── */
function ik(p: { x: number; y: number }, tx: number, ty: number, side: 1 | -1, prev?: { x: number; y: number }) {
  let dx = tx - p.x;
  let dy = ty - p.y;
  const d0 = Math.hypot(dx, dy) || 1e-4;
  const d = clamp(d0, Math.abs(L1 - L2) + 2, L1 + L2 - 0.3);
  dx = (dx / d0) * d;
  dy = (dy / d0) * d;
  const phi = Math.atan2(dy, dx);
  const a = Math.acos(clamp((L1 * L1 + d * d - L2 * L2) / (2 * L1 * d), -1, 1));
  const c1 = { x: p.x + L1 * Math.cos(phi + a), y: p.y + L1 * Math.sin(phi + a) };
  const c2 = { x: p.x + L1 * Math.cos(phi - a), y: p.y + L1 * Math.sin(phi - a) };
  // elbows point outward; when both bends are about equally good, keep the previous one so the arm never flips
  const score = (e: { x: number; y: number }) => side * (e.x - p.x) * 1.6 + 0.4 * (e.y - p.y);
  const s1 = score(c1);
  const s2 = score(c2);
  let e = s1 > s2 ? c1 : c2;
  if (prev && Math.abs(s1 - s2) < 18) {
    const d1 = Math.hypot(c1.x - prev.x, c1.y - prev.y);
    const d2 = Math.hypot(c2.x - prev.x, c2.y - prev.y);
    e = d1 < d2 ? c1 : c2;
  }
  return { e, h: { x: p.x + dx, y: p.y + dy } };
}

const BUBBLE_CSS = `
.prudie-wrap{position:relative}
:root[data-theme="dark"] .prudie-wrap>svg{filter:saturate(.86) brightness(1.05)}
.prudie-bubble{position:absolute;z-index:5;pointer-events:none;width:max-content;max-width:min(240px,80vw);
  padding:10px 14px;border-radius:16px;background:var(--color-raised,#fff);color:var(--color-ink,#333641);border:1.5px solid var(--color-line,#E4E4EC);
  box-shadow:0 8px 24px rgba(21,20,27,.16);font:500 14px/1.35 system-ui,-apple-system,'Segoe UI',sans-serif;
  opacity:0;transform:translateY(6px) scale(.92);transition:opacity .18s ease,transform .26s cubic-bezier(.3,1.5,.5,1)}
.prudie-bubble b{color:var(--color-accent,#4E65B5);font-weight:700}
.prudie-bubble.on{opacity:1;transform:none}
.prudie-bubble::after{content:"";position:absolute;width:12px;height:12px;background:var(--color-raised,#fff);border:1.5px solid var(--color-line,#E4E4EC);transform:rotate(45deg)}
.prudie-bubble.top{left:50%;bottom:100%;margin-bottom:6px;translate:-50% 0}
.prudie-bubble.top::after{left:calc(50% - 6px);bottom:-7px;border-top:0;border-left:0}
.prudie-bubble.left{right:100%;top:18%;margin-right:8px}
.prudie-bubble.left::after{right:-7px;top:16px;border-bottom:0;border-left:0}
.prudie-bubble.right{left:100%;top:18%;margin-left:8px}
.prudie-bubble.right::after{left:-7px;top:16px;border-top:0;border-right:0}
@media (prefers-reduced-motion:reduce){.prudie-bubble{transition:opacity .01s}}
`;

/* ───────────── mount ───────────── */
export function mountPrudie(container: HTMLElement, opts: PrudieOptions = {}): PrudieHandle {
  const id = ++uid;
  container.classList.add('prudie-wrap');
  if (!document.getElementById('prudie-css')) {
    const st = document.createElement('style');
    st.id = 'prudie-css';
    st.textContent = BUBBLE_CSS;
    document.head.appendChild(st);
  }
  container.insertAdjacentHTML('afterbegin', build(id));
  const svg = container.querySelector('svg') as SVGSVGElement;
  const q = (k: string) => svg.querySelector(`[data-k="${k}"]`) as SVGElement;

  const greeting = opts.greeting ?? "Hi, I'm Prudie! How can I assist you today?";
  const doneLines = opts.doneLines ?? ['Task done!', "Done! What's next?"];
  const idleEvery = opts.idleEvery === undefined ? ([2, 3] as [number, number]) : opts.idleEvery;
  const idleFirst = opts.idleFirstAfter ?? 2;
  const idlePool = (opts.idleActions ?? IDLE_ACTIONS).slice();

  const bubbleEl = document.createElement('div');
  bubbleEl.className = `prudie-bubble ${opts.bubble ?? 'top'}`;
  bubbleEl.setAttribute('role', 'status');
  container.appendChild(bubbleEl);
  let bubbleText = '';
  function renderText(text: string) {
    if (text === bubbleText) return;
    bubbleText = text;
    bubbleEl.textContent = '';
    const m = text.match(/^(.*?)(Prudie)(.*)$/);
    if (m) {
      const b = document.createElement('b');
      b.textContent = m[2];
      bubbleEl.append(m[1], b, m[3]);
    } else bubbleEl.textContent = text;
  }
  let sayText = '';
  let sayUntil = -1;

  const handEls = (k: string) => ({
    root: q(k),
    pose: Object.fromEntries(POSES.map((p) => [p, q(k + p)])) as Record<Pose, SVGElement>,
    fingers: [0, 1, 2, 3].map((i) => q(`${k}f${i}`)),
  });

  const E = {
    shadow: q('shadow'), char: q('char'), head: q('head'), stand: q('stand'), prone: q('prone'),
    legPLs: q('legPLshin'), legPRs: q('legPRshin'), legR: q('legR'),
    face: q('face'), blushL: q('blushL'), blushR: q('blushR'),
    eyeL: q('eyeL'), eyeR: q('eyeR'), happyL: q('happyL'), happyR: q('happyR'), shutL: q('shutL'), shutR: q('shutR'),
    mouth: q('mouth'), whistle: q('whistle'), codeGlow: q('codeGlow'), codeLines: q('codeLines'), shine: q('shine'),
    glasses: q('glasses'), glassLed: q('glassLed'), hood: q('hood'), hoodTorso: q('hoodTorso'), phones: q('phones'),
    deck: q('deck'), lid: q('lid'), keys: Array.from(svg.querySelectorAll('[data-key]')) as SVGElement[],
    armLb: q('armLb'), armLm: q('armLm'), armLh: q('armLh'), elbowL: q('elbowL'),
    armRb: q('armRb'), armRm: q('armRm'), armRh: q('armRh'), elbowR: q('elbowR'),
    hL: handEls('hL'), hR: handEls('hR'),
    lens: q('lens'), lensFog: q('lensfog'), scan: q('scan'), hud: q('hud'), led: q('led'),
    burger: q('burger'), bites: [q('bite0'), q('bite0b'), q('bite1'), q('bite1b')],
    juice: q('juice'), straw: q('straw'), strawStripe: q('strawStripe'),
    cloth: q('cloth'), pocketCloth: q('pocketCloth'), puff: q('puff'),
    glyphs: q('glyphs'), gl: [q('gl0'), q('gl1'), q('gl2'), q('gl3')],
    notes: q('notes'), nt: [q('n0'), q('n1'), q('n2'), q('n3')],
    sparks: q('sparks'), sp: [q('sp0'), q('sp1'), q('sp2'), q('sp3')],
    xL: q('xL'), xR: q('xR'), heart: q('heart'), mask: q('mask'),
    zzz: q('zzz'), z: [q('z0'), q('z1'), q('z2')],
    board: q('board'), wheels: [q('wheel0'), q('wheel1')], dust: q('dust'), d: [q('d0'), q('d1'), q('d2')],
    phone: q('phone'), flash: q('flash'), console: q('console'), cscreen: q('cscreen'),
    cship: q('cship'), cfoe: q('cfoe'), cshot: q('cshot'), five: q('five'), fiveRing: q('fiveRing'),
  };

  const keyInfo = E.keys.map((el) => {
    const x = Number(el.getAttribute('x'));
    const w = Number(el.getAttribute('width'));
    const y = Number(el.getAttribute('y'));
    return { el, cx: x + w / 2, y, lit: -9 };
  });

  const NS = 'http://www.w3.org/2000/svg';
  const CODE_COLORS = [EYE_GLOW, CYAN, GOLD, EYE, PINK];
  const codeRows: SVGRectElement[] = [];
  for (let i = 0; i < 9; i++) {
    const r = document.createElementNS(NS, 'rect');
    r.setAttribute('height', '4');
    r.setAttribute('rx', '2');
    E.codeLines.appendChild(r);
    codeRows.push(r);
  }
  const typedLines: { w: number; x: number; c: string }[] = [{ w: 0, x: 92, c: CODE_COLORS[0] }];

  const reduced = typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  const amp = reduced ? 0.3 : 1;
  const follow = opts.followPointer !== false;
  const radius = opts.followRadius ?? 460;
  const oneShot = opts.oneShot !== false;

  const S = {} as Record<Key, Spring>;
  (Object.keys(BASE) as Key[]).forEach((k) => {
    const [kk, z] = CFG[k] ?? [150, 0.65];
    S[k] = { v: BASE[k], vel: 0, t: BASE[k], k: kk, z };
  });

  const poseState = {
    L: { cur: 'relax' as Pose, prev: 'relax' as Pose, at: -9 },
    R: { cur: 'relax' as Pose, prev: 'relax' as Pose, at: -9 },
  };
  const fingerPress = { L: [-9, -9, -9, -9], R: [-9, -9, -9, -9] };
  let lensHand: 'L' | 'R' = 'R';
  const prevElbow: { L?: { x: number; y: number }; R?: { x: number; y: number } } = {};

  let state: PrudieState = opts.state ?? 'idle';
  let stateT = 0;
  let endAt = -1;
  let now = 0;
  let last = 0;
  let raf = 0;
  let hovered = false;
  let hoverT = -9;
  let px = NaN;
  let py = NaN;
  let lookTarget: { x: number; y: number } | null = null;
  let blinkStart = -1;
  let nextBlink = 1.6;
  let wanderX = 0;
  let wanderY = 0;
  let nextWander = 2;
  let sacX = 0;
  let nextSac = 0;
  let touchTimer = 0;

  let idleAct: Exclude<IdleAction, 'wave'> | null = null;
  const napAfter = opts.napAfter === undefined ? 25 : opts.napAfter;
  const highFive = opts.highFive !== false;
  let lastActive = 0;
  let napping = false;
  let napT = -99;
  let wakeT = -99;
  let napPx = NaN;
  let napPy = NaN;
  let flashT = -99;
  let fiveT = -99;
  let palmUp = false;
  const fired = new Set<string>();
  const once = (k: string) => (fired.has(k) ? false : (fired.add(k), true));
  let idleT = 0;
  let nextIdle = 0;
  let lastIdle: IdleAction | null = null;

  const handKey = [14, 21];
  let tyNext = 0;
  let tyBurst = 6;
  let tyPauseUntil = 0;
  let lastHand = 1;

  const onMove = (e: PointerEvent) => {
    px = e.clientX;
    py = e.clientY;
    if (napping) {
      if (Number.isNaN(napPx)) {
        napPx = px;
        napPy = py;
      } else if (now - napT > 1.2 && Math.hypot(px - napPx, py - napPy) > 30) wake();
    } else lastActive = now;
  };
  if (follow) window.addEventListener('pointermove', onMove, { passive: true });

  function startNap() {
    if (napping) return;
    napping = true;
    napT = now;
    napPx = px;
    napPy = py;
    idleAct = null;
  }
  function wake() {
    if (!napping) return;
    napping = false;
    wakeT = now;
    lastActive = now;
    S.bodyY.vel -= 340;
    S.squash.vel += 5;
    scheduleIdle(true);
  }

  const onEnter = () => {
    hovered = true;
    hoverT = now;
    lastActive = now;
    if (napping) wake();
    if (idleAct) endIdle();
  };
  const onLeave = () => {
    hovered = false;
  };
  const poke = () => {
    S.bodyY.vel -= 320;
    S.squash.vel += 6;
    S.tilt.vel += (Math.random() < 0.5 ? -1 : 1) * 60;
  };
  const onDown = (e: PointerEvent) => {
    lastActive = now;
    if (napping) {
      wake();
      return;
    }
    if (palmUp && state === 'idle') {
      fiveT = now;
      sayText = 'High five!';
      sayUntil = now + 1.4;
      S.bodyY.vel -= 220;
      return;
    }
    poke();
    if (e.pointerType !== 'mouse') {
      onEnter();
      clearTimeout(touchTimer);
      touchTimer = window.setTimeout(onLeave, 3200);
    }
  };
  container.addEventListener('pointerenter', onEnter);
  container.addEventListener('pointerleave', onLeave);
  container.addEventListener('pointerdown', onDown);

  function scheduleIdle(first = false) {
    nextIdle = idleEvery ? now + (first ? idleFirst : rand(idleEvery[0], idleEvery[1])) : Infinity;
  }
  function endIdle() {
    idleAct = null;
    scheduleIdle();
  }
  function startIdle(a: IdleAction) {
    lastIdle = a;
    fired.clear();
    if (a === 'wave') {
      setState('wave');
      return;
    }
    idleAct = a;
    idleT = now;
  }
  // Shuffle bag: every action plays once before any repeats, so all of them show up as fast as possible.
  let bag: IdleAction[] = [];
  // Opening routine: on a fresh mount these four play first, in this order, and Prudie cannot nap until they are done.
  const intro = (['snack', 'music', 'polish', 'wipe'] as IdleAction[]).filter((x) => idlePool.includes(x));
  function pickIdle(): IdleAction | null {
    if (!idlePool.length) return null;
    if (intro.length) return intro.shift()!;
    if (!bag.length) {
      bag = idlePool.slice();
      for (let i = bag.length - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1));
        [bag[i], bag[j]] = [bag[j], bag[i]];
      }
      if (bag.length > 1 && bag[bag.length - 1] === lastIdle) [bag[0], bag[bag.length - 1]] = [bag[bag.length - 1], bag[0]];
    }
    return bag.pop() ?? null;
  }

  function setState(s: PrudieState) {
    const was = state;
    lastActive = now;
    if (napping) {
      napping = false;
      wakeT = now;
    }
    fired.clear();
    state = s;
    stateT = now;
    idleAct = null;
    endAt = oneShot && ONE_SHOT[s] ? now + ONE_SHOT[s]! : -1;
    if (s === 'wave' || s === 'thumbsup') S.bodyY.vel -= 240;
    if (s === 'idle' && was !== 'idle') scheduleIdle(true);
  }

  function headCenter() {
    const r = svg.getBoundingClientRect();
    return { x: r.left + r.width * 0.5, y: r.top + r.height * 0.4, w: r.width };
  }

  function pointerGaze() {
    if (!follow || Number.isNaN(px)) return { x: 0, y: 0, on: 0 };
    const c = headCenter();
    const dx = px - c.x;
    const dy = py - c.y;
    const w = clamp((radius - Math.hypot(dx, dy)) / (radius * 0.15), 0, 1);
    const reach = Math.max(120, c.w * 0.9);
    return { x: clamp(dx / reach, -1, 1) * w, y: clamp(dy / reach, -1, 1) * w, on: w };
  }

  function bubbleFor(ts: number): string {
    if (now < sayUntil) return sayText;
    if (state === 'thumbsup' && doneLines.length) {
      if (ts > 0.35 && (!oneShot || ts < ONE_SHOT.thumbsup! - 0.2)) {
        return doneLines[Math.min(doneLines.length - 1, Math.floor((ts - 0.35) / 1.5))];
      }
      return '';
    }
    // greet after landing from the skate-in, and whenever Prudie is idle and not busy with anything (hover or not)
    if (greeting && state === 'skate' && ts > 1.4) return greeting;
    if (greeting && state === 'idle' && !idleAct && !napping) return greeting;
    return '';
  }

  /** one key press: choose hand + key, move the hand there, press one finger, light the key */
  function keystroke() {
    const h = Math.random() < 0.72 ? 1 - lastHand : lastHand;
    lastHand = h;
    let k: number;
    if (Math.random() < 0.08) {
      k = 36;
    } else {
      const row = Math.floor(rand(0, 3));
      const col = h ? Math.floor(rand(6, 12)) : Math.floor(rand(0, 6));
      k = row * 12 + col;
    }
    handKey[h] = k;
    keyInfo[k].lit = now;
    const col = k === 36 ? (h ? 6 : 5) : k % 12;
    const local = h ? col - 6 : 5 - col;
    const fi = clamp(Math.floor(local * 0.7), 0, 3);
    (h ? fingerPress.R : fingerPress.L)[fi] = now;
    S[h ? 'ry' : 'ly'].vel += 70;
    const line = typedLines[typedLines.length - 1];
    line.w += rand(3, 7);
    if (line.w > rand(60, 104)) {
      S.hy.vel += 40;
      typedLines.push({ w: 0, x: 92 + Math.floor(rand(0, 3)) * 8, c: CODE_COLORS[Math.floor(rand(0, CODE_COLORS.length))] });
      if (typedLines.length > 9) typedLines.shift();
      tyPauseUntil = now + rand(0.35, 0.8);
    }
  }

  function targets(ts: number, t: number): Targets {
    const T: Targets = { ...BASE, poseL: 'relax', poseR: 'relax', lensHand: 'R' };
    const sway = Math.sin(t * 1.7) * 1.5 * amp;
    T.lx = REST_L.x + Math.sin(t * 1.3) * 1.2 * amp;
    T.ly = REST_L.y + sway;
    T.rx = REST_R.x - Math.sin(t * 1.3) * 1.2 * amp;
    T.ry = REST_R.y - sway;
    T.tilt = Math.sin(t * 0.9) * 1.4 * amp;

    const pg = pointerGaze();
    let gx = pg.x;
    let gy = pg.y;
    let headFollow = 1;
    if (t > nextWander) {
      wanderX = (Math.random() * 2 - 1) * 0.3;
      wanderY = (Math.random() * 2 - 1) * 0.2;
      nextWander = t + 2.4 + Math.random() * 3.2;
    }
    if (pg.on < 0.05) {
      gx += wanderX;
      gy += wanderY;
    }

    switch (state) {
      case 'idle': {
        if (napping) {
          // asleep: sleep mask on, head drooping, slow breathing, zzz
          const nt = now - napT;
          T.mask = nt > 0.3 ? 1 : 0;
          if (nt < 0.9) {
            T.lx = 112;
            T.ly = 150;
            T.rx = 188;
            T.ry = 150;
            T.poseL = 'back';
            T.poseR = 'back';
          }
          T.nap = nt > 0.9 ? 1 : 0;
          T.tilt = nt > 0.9 ? 8 + Math.sin(t * 1.1) * 1.5 : 0;
          T.hy = nt > 0.9 ? 8 + Math.sin(t * 1.1) * 2 : 0;
          T.lean = 1.5;
          T.mouth = 0.5;
          T.mw = 3.5;
          T.mc = 0;
          T.mo = 1.6 + Math.sin(t * 1.1) * 0.8;
          T.squash = Math.sin(t * 1.1) * 0.02;
          gx = 0;
          gy = 0;
          headFollow = 0;
          break;
        }
        if (now - wakeT < 1.3) {
          // just woke up: startled, wide eyes, double blink
          const wt = now - wakeT;
          T.squint = -0.25;
          T.mo = 4;
          T.mw = 5;
          T.mc = 0;
          T.lx = 70;
          T.ly = 222;
          T.rx = 230;
          T.ry = 222;
          T.poseL = 'open';
          T.poseR = 'open';
          if ((wt > 0.5 && wt < 0.62) || (wt > 0.75 && wt < 0.87)) T.squint = 1.6;
          gx *= 0.2;
          gy *= 0.2;
          break;
        }
        // cursor close by: raise the right palm for a high five
        let near = false;
        if (highFive && follow && !idleAct && !Number.isNaN(px)) {
          const r = svg.getBoundingClientRect();
          near = px > r.left - 50 && px < r.right + 50 && py > r.top - 50 && py < r.bottom + 50;
        }
        palmUp = near;
        const fiveAge = now - fiveT;
        if (near || fiveAge < 0.9) {
          T.rx = 242 + (fiveAge < 0.25 ? 6 : 0);
          T.ry = 182;
          T.poseR = 'open';
          T.happy = fiveAge < 0.9 ? 1 : 0;
          T.blush = 0.8;
          T.mc = 7;
          T.mw = 10;
          T.mo = 3;
        }
        if (hovered && !idleAct) {
          const hv = now - hoverT;
          T.mc = 7;
          T.mw = 10;
          T.mo = 3;
          T.blush = 0.75;
          T.tilt += 4 + Math.sin(hv * 7) * Math.exp(-hv * 2.2) * 4;
          gx *= 0.35;
          gy *= 0.35;
          break;
        }
        if (!idleAct) break;
        const it = now - idleT;
        headFollow = 0;

        if (idleAct === 'snack') {
          T.burger = it < 5.8 ? 1 : 0;
          T.poseR = 'fist';
          if (it < 2.7) {
            const toMouth = it > 0.55;
            T.rx = toMouth ? 184 : 200;
            T.ry = toMouth ? 222 : 240;
            T.hy = toMouth ? 14 : 0;
            T.tilt = toMouth ? -3 : 0;
            gx = 0.3;
            gy = 0.75;
            const chew = it > 1.0;
            T.mo = chew ? 2 + Math.abs(Math.sin(it * 13)) * 5 : 4;
            T.mw = 8;
            T.mc = 3;
            if ((it > 1.05 && it < 1.2) || (it > 1.85 && it < 2.0)) S.rx.vel -= 70;
          } else {
            T.rx = 216;
            T.ry = 256;
          }
          T.juice = it > 2.6 && it < 5.8 ? 1 : 0;
          if (it > 2.6) T.poseL = 'fist';
          if (it > 2.9 && it < 4.8) {
            T.lx = 126;
            T.ly = 228;
            T.hy = 12;
            T.happy = 1;
            T.blush = 0.95;
            T.mo = 2.5;
            T.mw = 3;
            T.mc = 0;
          } else if (it > 2.6) {
            T.lx = 104;
            T.ly = 250;
          }
          if (it > 4.8 && it < 6.2) {
            T.happy = 1;
            T.mc = 8;
            T.mw = 10;
            T.mo = 2;
            T.blush = 0.9;
          }
          if (it > IDLE_LEN.snack) endIdle();
        } else if (idleAct === 'polish') {
          // left hand holds the lens; right hand takes the napkin from the hip pocket and rubs it
          T.lensHand = 'L';
          T.lens = it < 5.2 ? 1 : 0;
          T.poseL = 'fist';
          const checking = it > 4.0;
          T.lx = checking ? 96 : 126;
          T.ly = checking ? 200 : 272;
          T.hy = it > 0.3 && it < 4.0 ? 12 : 0;
          gx = checking ? -0.45 : 0.05;
          gy = checking ? -0.2 : 0.85;
          if (it > 0.35 && it < 0.85) {
            T.mo = 5;
            T.mw = 5;
            T.mc = 0;
            T.puff = 1;
          }
          T.fog = it > 0.5 && it < 1.6 ? 1 : 0;
          T.poseR = 'fist';
          if ((it > 0.4 && it < 1.05) || (it > 3.55 && it < 4.0)) {
            T.rx = POCKET.x;
            T.ry = POCKET.y;
          }
          T.cloth = it > 1.0 && it < 3.65 ? 1 : 0;
          if (it > 1.05 && it < 3.55) {
            const w = (it - 1.05) * 9;
            T.rx = 158 + Math.cos(w) * 9;
            T.ry = 236 + Math.sin(w) * 7;
            T.squint = 0.3;
          }
          if (checking) {
            T.happy = 1;
            T.sparkle = it < 5.2 ? 0.7 : 0;
            T.mc = 7;
            T.mw = 9;
          }
          if (it > IDLE_LEN.polish) endIdle();
        } else if (idleAct === 'wipe') {
          // napkin from the hip pocket, wipe the screen face, put it back
          T.poseR = 'fist';
          const out = it > 0.6 && it < 3.8;
          T.cloth = out ? 1 : 0;
          if (it < 0.6 || (it > 3.55 && it < 4.0)) {
            T.rx = POCKET.x;
            T.ry = POCKET.y;
          } else if (out) {
            const w = (it - 1.0) * 7;
            const rub = it > 1.0 && it < 3.35;
            T.rx = 176 + (rub ? Math.sin(w) * 13 : 0);
            T.ry = 192 - (rub ? Math.abs(Math.cos(w)) * 4 : 0);
            T.hy = 26;
            T.tilt = 4 + (rub ? Math.sin(w) * -2 : 0);
            T.shut = rub ? 1 : 0;
            T.mo = rub ? 2 : 0;
          }
          T.shine = it > 3.15 ? 1 : 0;
          if (it > 4.0) {
            T.happy = 1;
            T.sparkle = it < 4.8 ? 0.7 : 0;
            T.mc = 8;
            T.mw = 10;
            T.blush = 0.8;
          }
          if (it > IDLE_LEN.wipe) endIdle();
        } else if (idleAct === 'selfie') {
          // phone out, arm up, peace sign, flash, heart eyes, check the photo, put it away
          T.phone = it < 5.2 ? 1 : 0;
          T.poseR = 'fist';
          if (it < 0.5 || it > 4.6) {
            T.rx = POCKET.x;
            T.ry = POCKET.y;
          } else if (it < 2.9) {
            T.rx = 252;
            T.ry = 176;
            T.lx = 70;
            T.ly = 200;
            T.poseL = 'peace';
            T.tilt = 7;
            T.hx = 4;
            T.happy = it > 0.9 ? 1 : 0;
            T.blush = 0.95;
            T.mc = 8;
            T.mw = 10;
            T.mo = 3;
            if (it > 1.6 && once('flash')) flashT = now;
            T.heart = it > 1.7 && it < 2.8 ? 1 : 0;
          } else {
            T.rx = 206;
            T.ry = 238;
            gx = 0.45;
            gy = 0.7;
            T.pglow = 1;
            T.mc = 6;
            T.mw = 8;
          }
          if (it > IDLE_LEN.selfie) endIdle();
        } else if (idleAct === 'scroll') {
          // doomscroll: thumb flicks up the feed, then a big XD laugh
          T.phone = it < 6.0 ? 1 : 0;
          T.poseR = 'fist';
          if (it < 0.5 || it > 5.4) {
            T.rx = POCKET.x;
            T.ry = POCKET.y;
          } else {
            T.rx = 192;
            T.ry = 248;
            T.pglow = 1;
            const laugh = it > 2.6 && it < 3.9;
            if (!laugh) {
              const flick = ((it * 1.5) % 1);
              T.lx = 170;
              T.ly = 240 - flick * 12;
              T.poseL = 'back';
              gx = 0.35;
              gy = 0.85;
              T.squint = 0.25;
              T.mw = 4;
              T.mc = 1;
            } else {
              T.xd = 1;
              T.mo = 8;
              T.mc = 6;
              T.mw = 11;
              T.blush = 1;
              T.bodyY = Math.sin(t * 28) * 2.5 * amp;
              T.tilt = Math.sin(t * 22) * 2.5 * amp - 4;
              T.lx = 108;
              T.ly = 254;
            }
          }
          if (it > IDLE_LEN.scroll) endIdle();
        } else if (idleAct === 'game') {
          // handheld console: button mashing with a squint, then a win
          T.game = it < 6.2 ? 1 : 0;
          T.poseL = 'fist';
          T.poseR = 'fist';
          const win = it > 4.1 && it < 5.6;
          if (!win) {
            T.lx = 108 + (it > 0.6 ? Math.sin(t * 37) * 2.2 : 0);
            T.ly = 250 + (it > 0.6 ? Math.cos(t * 41) * 2.2 : 0);
            T.rx = 192 + (it > 0.6 ? Math.sin(t * 43 + 1) * 2.2 : 0);
            T.ry = 250 + (it > 0.6 ? Math.cos(t * 31 + 2) * 2.2 : 0);
            gx = Math.sin(t * 5) * 0.2;
            gy = 0.95;
            T.squint = 0.75;
            T.mw = 4;
            T.mc = -1.5;
            T.hy = 6;
            T.tilt = Math.sin(t * 3) * 3 * amp;
          } else {
            T.lx = 108;
            T.ly = 198;
            T.rx = 192;
            T.ry = 198;
            T.happy = 1;
            T.sparkle = 1;
            T.mc = 9;
            T.mw = 11;
            T.mo = 6;
            T.blush = 0.9;
            if (once('win')) {
              S.bodyY.vel -= 300;
              sayText = 'GG!';
              sayUntil = now + 1.3;
            }
          }
          if (it > IDLE_LEN.game) endIdle();
        } else if (idleAct === 'music') {
          T.phones = it > 0.25 && it < 6.9 ? 1 : 0;
          if (it < 0.9) {
            T.lx = 70;
            T.ly = 172;
            T.rx = 230;
            T.ry = 172;
            T.poseL = 'back';
            T.poseR = 'back';
          }
          const playing = it > 0.9 && it < 6.9;
          if (playing) {
            const beat = Math.sin((it - 0.9) * Math.PI * 2 * 1.8);
            T.happy = 1;
            T.notes = 1;
            T.tilt = beat * 5 * amp;
            T.hx = beat * 3 * amp;
            T.lean = beat * 1.5 * amp;
            T.whistle = 1;
            T.mouth = 0;
            T.blush = 0.8;
            T.tap = Math.max(0, beat);
            T.lx = 64;
            T.ly = 176;
            T.poseL = 'back';
            T.rx = 216;
            T.ry = 262 - Math.max(0, beat) * 8;
          }
          if (it > IDLE_LEN.music) endIdle();
        }
        break;
      }

      case 'skate': {
        // roll in on a skateboard, brake, hop off, wave
        if (ts < 1.75) {
          T.board = 1;
          T.lx = 66;
          T.ly = 236;
          T.rx = 234;
          T.ry = 236;
          T.poseL = 'back';
          T.poseR = 'back';
          T.lean = ts < 1.2 ? 4 : -7;
          T.tilt = ts < 1.2 ? 3 : -4;
          gx = ts < 1.2 ? 0.7 : 0;
          T.happy = ts < 1.2 ? 0.7 : 0;
          T.mc = 6;
          T.mw = 8;
          T.mo = ts > 1.2 ? 4 : 2;
        }
        if (ts > 1.75 && once('hop')) S.bodyY.vel -= 330;
        if (ts > 2.1 && ts < 3.7) {
          const w = (ts - 2.1) * 10;
          T.rx = 238 + Math.sin(w) * 3 * amp;
          T.ry = 176;
          T.wristR = Math.sin(w) * 22 * amp;
          T.poseR = 'open';
          T.happy = 0.85;
          T.mc = 7;
          T.mw = 10;
          T.mo = 4;
          T.blush = 0.8;
          T.tilt = -5;
        }
        break;
      }

      case 'wave': {
        const w = ts * 10;
        const up = ts > 0.2 && ts < 2.5;
        if (up) {
          T.rx = 238 + Math.sin(w) * 3 * amp;
          T.ry = 176;
          T.wristR = Math.sin(w) * 22 * amp;
          T.poseR = 'open';
        }
        T.happy = up ? 0.85 : 0;
        T.mc = 7;
        T.mw = 10;
        T.mo = 4;
        T.blush = 0.8;
        T.tilt = up ? -5 : 0;
        T.lean = up ? 1.5 : 0;
        gx *= 0.3;
        gy *= 0.3;
        break;
      }

      case 'search': {
        T.glasses = ts > 0.1 ? 1 : 0;
        const lensOn = ts > 0.95;
        const sweeping = ts > 1.35;
        T.lens = lensOn ? 1 : 0;
        if (ts > 0.1 && ts < 0.9) {
          // touch the side of the glasses to switch them on
          T.rx = 226;
          T.ry = 160;
          T.poseR = 'back';
          T.tilt = -3;
        }
        if (lensOn) {
          T.poseR = 'fist';
          const s = sweeping ? Math.sin((ts - 1.35) * 1.8) : 0;
          T.rx = 194 + s * 32;
          T.ry = 194 + (sweeping ? Math.sin(ts * 3.6) * 3 : 0);
          gx = clamp((T.rx + LENS_OFF.x - 150) / 48, -1, 1);
          gy = clamp((T.ry - 6 + LENS_OFF.y - 124) / 50, -1, 1);
          T.tilt = s * 3 * amp;
          T.lean = -s * 1.2 * amp;
        }
        T.mc = 1;
        T.mw = 5;
        T.mo = 3.5;
        headFollow = 0;
        break;
      }

      case 'code': {
        T.hood = ts > 0.1 ? 1 : 0;
        T.phones = ts > 1.0 ? 1 : 0;
        T.laptop = ts > 1.8 ? 1 : 0;
        const typing = ts > 2.3;
        if (ts > 0.1 && ts < 0.85) {
          T.lx = 112;
          T.ly = 204;
          T.rx = 188;
          T.ry = 204;
          T.poseL = 'fist';
          T.poseR = 'fist';
        }
        if (ts > 1.0 && ts < 1.75) {
          T.lx = 70;
          T.ly = 172;
          T.rx = 230;
          T.ry = 172;
          T.poseL = 'back';
          T.poseR = 'back';
          T.tilt = Math.sin(ts * 10) * 2;
        }
        if (ts > 1.75) {
          const kl = keyInfo[handKey[0]];
          const kr = keyInfo[handKey[1]];
          T.lx = kl.cx;
          T.ly = kl.y - 19;
          T.rx = kr.cx;
          T.ry = kr.y - 19;
          T.poseL = 'type';
          T.poseR = 'type';
        }
        if (typing) {
          const reading = now < tyPauseUntil;
          if (!reading && now > tyNext) {
            keystroke();
            if (--tyBurst <= 0) {
              tyBurst = Math.floor(rand(4, 13));
              tyPauseUntil = now + rand(0.4, 1.1);
            }
            tyNext = now + rand(0.08, 0.17);
          }
          gx = reading ? Math.sin(t * 3) * 0.35 : (keyInfo[handKey[lastHand]].cx - 150) / 70;
          gy = reading ? 0.45 : 0.85;
          T.squint = reading ? 0.2 : 0.4;
          T.glow = 1;
          T.mw = 5;
          T.mc = reading ? 4 : 2;
          T.hy = reading ? 0 : 3;
          T.tilt = Math.sin(t * 6.3) * 1.2 * amp;
        }
        headFollow = 0;
        break;
      }

      case 'thumbsup': {
        const upH = !oneShot ? ts > 0.18 : ts > 0.18 && ts < ONE_SHOT.thumbsup! - 0.35;
        T.rx = upH ? 244 : REST_R.x;
        T.ry = upH ? 214 : REST_R.y;
        if (upH) T.poseR = 'thumb';
        T.sparkle = upH ? 1 : 0;
        T.happy = upH ? 1 : 0;
        T.mc = 9;
        T.mw = 11;
        T.mo = 6;
        T.blush = 0.9;
        T.tilt = upH ? -4 : 0;
        T.squash = ts < 0.18 ? 0.1 : 0;
        gx *= 0.2;
        gy *= 0.2;
        break;
      }

      case 'look': {
        if (t > nextSac) {
          sacX = (Math.random() * 2 - 1) * 0.3;
          nextSac = t + 0.4 + Math.random() * 0.7;
        }
        let bx = 0;
        if (lookTarget) {
          const c = headCenter();
          bx = clamp((lookTarget.x - c.x) / (c.w * 0.8), -1, 1);
        }
        T.prone = 1;
        gx = clamp(bx * 0.8 + sacX, -1, 1);
        gy = 1;
        T.tilt = bx * 5 + Math.sin(t * 1.6) * 2.5 * amp;
        T.lx = 76;
        T.ly = 286 + Math.sin(t * 1.6) * 1.5;
        T.rx = 224;
        T.ry = 286 - Math.sin(t * 1.6) * 1.5;
        T.poseL = 'back';
        T.poseR = 'back';
        T.wristL = 14;
        T.wristR = -14;
        T.mc = 5;
        T.mw = 7;
        T.blush = 0.7;
        headFollow = 0;
        break;
      }
    }

    gx = clamp(gx, -1, 1);
    gy = clamp(gy, -1, 1);
    T.gx = gx;
    T.gy = gy;
    T.tilt += gx * 2.4 * headFollow;
    T.hx += gx * 3 * headFollow;
    T.hy += gy * 2 * headFollow;
    return T;
  }

  function stepSprings(dt: number, T: Targets) {
    const sub = 3;
    const h = dt / sub;
    (Object.keys(S) as Key[]).forEach((k) => {
      const s = S[k];
      s.t = T[k];
      const damp = 2 * Math.sqrt(s.k) * s.z;
      for (let i = 0; i < sub; i++) {
        s.vel += (s.k * (s.t - s.v) - damp * s.vel) * h;
        s.v += s.vel * h;
      }
    });
    for (const [side, p] of [
      ['L', T.poseL],
      ['R', T.poseR],
    ] as const) {
      const ps = poseState[side];
      if (ps.cur !== p) {
        ps.prev = ps.cur;
        ps.cur = p;
        ps.at = now;
      }
    }
    lensHand = T.lensHand;
  }

  function blinkValue(t: number) {
    if (blinkStart < 0 && t > nextBlink) blinkStart = t;
    if (blinkStart >= 0) {
      const u = (t - blinkStart) / 0.16;
      if (u >= 1) {
        blinkStart = -1;
        nextBlink = t + 2.2 + Math.random() * 3.5;
        return 0;
      }
      return 1 - Math.abs(u * 2 - 1);
    }
    return 0;
  }

  function drawHand(
    H: ReturnType<typeof handEls>,
    side: 'L' | 'R',
    e: { x: number; y: number },
    h: { x: number; y: number },
    wrist: number,
  ) {
    const ps = poseState[side];
    const u = clamp((now - ps.at) / 0.08, 0, 1);
    const forearm = (Math.atan2(h.y - e.y, h.x - e.x) * 180) / Math.PI;
    const natural = POSE_UP[ps.cur] ? -90 : 90;
    const lim = ps.cur === 'thumb' ? 0 : ps.cur === 'fist' || ps.cur === 'peace' ? 18 : 38;
    const rot = clamp(angDiff(forearm - natural), -lim, lim) + wrist;
    const mir = side === 'L' ? -1 : 1;
    const sc = ps.cur === 'thumb' ? 1.5 : ps.cur === 'peace' ? 1.38 : 1.22;
    H.root.setAttribute('transform', `translate(${f1(h.x)} ${f1(h.y)}) rotate(${f1(rot)}) scale(${(mir * sc).toFixed(2)} ${sc})`);
    for (const p of POSES) {
      const o = p === ps.cur ? u : p === ps.prev ? 1 - u : 0;
      H.pose[p].setAttribute('opacity', o.toFixed(2));
      H.pose[p].setAttribute('display', o > 0.01 ? 'inline' : 'none');
    }
    const presses = side === 'L' ? fingerPress.L : fingerPress.R;
    for (let i = 0; i < 4; i++) {
      const k = clamp(1 - (now - presses[i]) / 0.12, 0, 1);
      H.fingers[i].setAttribute('transform', `translate(0 ${f1(k * 3.5)})`);
    }
  }

  function render(t: number) {
    const v = (k: Key) => S[k].v;
    const op = (k: Key) => clamp(v(k), 0, 1);

    const pr = op('prone');
    const breathe = Math.sin(t * 2.1) * 0.012 * amp;
    const float = Math.sin(t * 1.5) * 2.4 * amp * (1 - pr) * (1 - op('laptop'));
    const sq = v('squash');
    const sx = 1 + sq * 0.5 - breathe * 0.5;
    const sy = 1 - sq * 0.6 + breathe;
    // skate-in: roll from the left, ease to a stop
    let skx = 0;
    if (state === 'skate') {
      const ts = now - stateT;
      const u = clamp(ts / 1.35, 0, 1);
      skx = -300 * Math.pow(1 - u, 3);
    }
    E.shadow.setAttribute('transform', `translate(${f1(skx)} 0)`);
    E.char.setAttribute(
      'transform',
      `translate(${f1(skx)} ${f1(v('bodyY') + float)}) translate(150 308) rotate(${f1(v('lean'))}) scale(${sx.toFixed(3)} ${sy.toFixed(3)}) translate(-150 -308)`,
    );
    const lift = -(v('bodyY') + float);
    E.shadow.setAttribute('rx', f1(clamp(64 - lift * 0.9, 44, 72) + pr * 34));
    E.shadow.setAttribute('opacity', clamp(0.16 - clamp(lift, -6, 14) * 0.004, 0.06, 0.2).toFixed(3));

    E.stand.setAttribute('opacity', (1 - pr).toFixed(2));
    E.stand.setAttribute('transform', `translate(0 ${f1(pr * 40)}) scale(1 ${(1 - pr * 0.5).toFixed(3)})`);
    E.prone.setAttribute('opacity', clamp(pr * 1.6 - 0.4, 0, 1).toFixed(2));
    E.prone.setAttribute('transform', `translate(0 ${f1((1 - pr) * 40)})`);
    // each leg on its own side, swinging back and forth in turn
    const kick = Math.sin(t * 3.6) * 18 * amp;
    E.legPLs.setAttribute('transform', `translate(0 ${f1(-kick * 0.7)}) rotate(${f1(kick * 0.6)} 112 166)`);
    E.legPRs.setAttribute('transform', `translate(0 ${f1(kick * 0.7)}) rotate(${f1(kick * 0.6)} 188 166)`);
    E.legR.setAttribute('transform', `rotate(${f1(-v('tap') * 8)} 160 304)`);

    const hdY = v('hy') + pr * PRONE_DROP;
    E.head.setAttribute('transform', `translate(${f1(v('hx'))} ${f1(hdY)}) rotate(${f1(v('tilt'))} ${PIVOT.x} ${PIVOT.y})`);

    const gx = clamp(v('gx'), -1.1, 1.1);
    const gy = clamp(v('gy'), -1.1, 1.1);
    const ex = gx * 15;
    const ey = gy * 13;
    E.face.setAttribute('transform', `translate(${f1(ex)} ${f1(ey)})`);

    const shL = { x: lerp(SH_L.x, SH_L_PRONE.x, pr), y: lerp(SH_L.y, SH_L_PRONE.y, pr) };
    const shR = { x: lerp(SH_R.x, SH_R_PRONE.x, pr), y: lerp(SH_R.y, SH_R_PRONE.y, pr) };
    const L = ik(shL, v('lx'), v('ly'), -1, prevElbow.L);
    const R = ik(shR, v('rx'), v('ry'), 1, prevElbow.R);
    prevElbow.L = L.e;
    prevElbow.R = R.e;

    // lens position (which hand holds it)
    const lvis = op('lens');
    const lh = lensHand === 'L' ? L.h : R.h;
    const lmir = lensHand === 'L' ? -1 : 1;
    const lsc = 0.55 + lvis * 0.45;
    const lcx = lh.x + LENS_OFF.x * lsc * lmir;
    const lcy = lh.y - 6 + LENS_OFF.y * lsc;

    // eyes
    const blink = blinkValue(t);
    const hp = op('happy');
    const shut = op('shut');
    const sqz = v('squint');
    const eyeSy = clamp((1 - blink) * (1 - sqz * 0.55), 0.08, 1.15);
    const fxS = 1 - Math.abs(gx) * 0.1;
    const searching = state === 'search' ? 1 : 0;
    const magAt = (cx: number, cy: number) =>
      1 + 0.4 * lvis * searching * Math.exp(-(((lcx - cx - ex) / 24) ** 2 + ((lcy - cy - ey - hdY) / 28) ** 2));
    const ls = magAt(EYE_L.x, EYE_L.y);
    const rs = magAt(EYE_R.x, EYE_R.y);
    E.eyeL.setAttribute('transform', `translate(${EYE_L.x} ${EYE_L.y}) scale(${(fxS * ls).toFixed(3)} ${(eyeSy * ls).toFixed(3)})`);
    E.eyeR.setAttribute('transform', `translate(${EYE_R.x} ${EYE_R.y}) scale(${(fxS * rs).toFixed(3)} ${(eyeSy * rs).toFixed(3)})`);
    const eyeOp = (1 - hp) * (1 - shut) * (1 - op('xd')) * (1 - op('heart'));
    E.eyeL.setAttribute('opacity', eyeOp.toFixed(2));
    E.eyeR.setAttribute('opacity', eyeOp.toFixed(2));
    for (const [el, p, o] of [
      [E.happyL, EYE_L, hp * (1 - shut) * (1 - op('heart'))],
      [E.happyR, EYE_R, hp * (1 - shut) * (1 - op('heart'))],
      [E.shutL, EYE_L, shut],
      [E.shutR, EYE_R, shut],
    ] as const) {
      el.setAttribute('transform', `translate(${p.x} ${p.y})`);
      el.setAttribute('opacity', o.toFixed(2));
    }
    const bl = clamp(v('blush'), 0, 1);
    E.blushL.setAttribute('opacity', bl.toFixed(2));
    E.blushR.setAttribute('opacity', bl.toFixed(2));

    const mw = clamp(v('mw'), 2.5, 14);
    const mc = v('mc');
    const mo = Math.max(0, v('mo'));
    E.mouth.setAttribute(
      'd',
      `M${f1(150 - mw)} ${MOUTH_Y} Q150 ${f1(MOUTH_Y + mc)} ${f1(150 + mw)} ${MOUTH_Y} Q150 ${f1(MOUTH_Y + mc + mo * 2.2)} ${f1(150 - mw)} ${MOUTH_Y}Z`,
    );
    E.mouth.setAttribute('opacity', op('mouth').toFixed(2));
    const xd = op('xd');
    const ht = op('heart');
    for (const [el, p] of [
      [E.xL, EYE_L],
      [E.xR, EYE_R],
    ] as const) {
      el.setAttribute('transform', `translate(${p.x} ${p.y})`);
      el.setAttribute('opacity', xd.toFixed(2));
    }
    E.heart.setAttribute('opacity', ht.toFixed(2));
    E.heart.setAttribute('transform', `translate(150 124) scale(${(0.8 + ht * 0.2 + Math.sin(t * 9) * 0.04 * ht).toFixed(3)}) translate(-150 -124)`);
    const wh = op('whistle');
    E.whistle.setAttribute('opacity', wh.toFixed(2));
    E.whistle.setAttribute('r', f1(3.2 + Math.sin(t * 11) * 0.6));

    const sh = v('shine');
    E.shine.setAttribute('opacity', (Math.sin(clamp(sh, 0, 1) * Math.PI) * 0.35).toFixed(2));
    E.shine.setAttribute('transform', `translate(${f1(60 + sh * 220)} 0)`);

    const gl = v('glasses');
    E.glasses.setAttribute('opacity', clamp(gl * 1.3, 0, 1).toFixed(2));
    E.glasses.setAttribute('transform', `translate(${f1(ex * 0.25)} ${f1((1 - gl) * -46 + ey * 0.2)}) rotate(${f1((1 - gl) * -10)} 150 120)`);
    E.glassLed.setAttribute('opacity', (0.55 + Math.sin(t * 5) * 0.45).toFixed(2));

    const ho = v('hood');
    const hoc = clamp(ho, 0, 1);
    E.hood.setAttribute('opacity', clamp(ho * 1.4, 0, 1).toFixed(2));
    E.hood.setAttribute('transform', `translate(0 ${f1((1 - ho) * -60)})`);
    E.hoodTorso.setAttribute('opacity', clamp(ho * 1.4, 0, 1).toFixed(2));
    E.hoodTorso.setAttribute('transform', `translate(0 ${f1((1 - ho) * -40)})`);
    const ph = v('phones');
    E.phones.setAttribute('opacity', clamp(ph * 1.5, 0, 1).toFixed(2));
    E.phones.setAttribute('transform', `translate(0 ${f1((1 - ph) * -70)}) translate(150 148) scale(${lerp(0.95, 1, hoc).toFixed(3)} ${lerp(0.78, 1, hoc).toFixed(3)}) translate(-150 -148)`);

    const lp = v('laptop');
    const lpo = clamp(lp * 1.4, 0, 1).toFixed(2);
    const lpt = `translate(0 ${f1((1 - lp) * 90)})`;
    E.deck.setAttribute('opacity', lpo);
    E.deck.setAttribute('transform', lpt);
    E.lid.setAttribute('opacity', lpo);
    E.lid.setAttribute('transform', lpt);
    for (const k of keyInfo) {
      const a = clamp(1 - (now - k.lit) / 0.22, 0, 1);
      const want = a > 0 ? mix(GRAPH, EYE_GLOW, a) : GRAPH;
      if (k.el.getAttribute('fill') !== want) k.el.setAttribute('fill', want);
    }

    const cg = op('glow');
    E.codeGlow.setAttribute('opacity', (Math.max(cg, op('pglow') * 0.8) * (0.7 + Math.sin(t * 3) * 0.1)).toFixed(2));
    E.codeLines.setAttribute('opacity', (cg * 0.3).toFixed(2));
    const nL = typedLines.length;
    for (let i = 0; i < codeRows.length; i++) {
      const line = typedLines[nL - 1 - i];
      const r = codeRows[i];
      if (!line) {
        r.setAttribute('width', '0');
        continue;
      }
      r.setAttribute('x', String(line.x));
      r.setAttribute('y', String(172 - i * 11));
      r.setAttribute('width', f1(line.w));
      r.setAttribute('fill', line.c);
    }
    E.glyphs.setAttribute('opacity', cg.toFixed(2));
    for (let i = 0; i < 4; i++) {
      const phz = (t * 0.45 + i / 4) % 1;
      E.gl[i].setAttribute('x', f1([28, 272, 18, 282][i] + Math.sin(t * 2 + i * 2) * 4));
      E.gl[i].setAttribute('y', f1([262, 254, 214, 206][i] - phz * 64));
      E.gl[i].setAttribute('opacity', (Math.sin(phz * Math.PI) * 0.95).toFixed(2));
    }

    // arms
    const dL = `M${f1(shL.x)} ${f1(shL.y)} L${f1(L.e.x)} ${f1(L.e.y)} L${f1(L.h.x)} ${f1(L.h.y)}`;
    const dR = `M${f1(shR.x)} ${f1(shR.y)} L${f1(R.e.x)} ${f1(R.e.y)} L${f1(R.h.x)} ${f1(R.h.y)}`;
    const wB = f1(lerp(19, 30, hoc));
    const wM = f1(lerp(16, 26.5, hoc));
    const cB = mix(SHELL_LO, HOOD_LO, hoc);
    const cM = mix(SHELL, HOOD, hoc);
    const cH = mix(SHELL_HI, HOOD_HI, hoc);
    const armOp = 1 - clamp(pr * 1.6, 0, 1);
    for (const [b, m, hl, p] of [
      [E.armLb, E.armLm, E.armLh, dL],
      [E.armRb, E.armRm, E.armRh, dR],
    ] as const) {
      b.setAttribute('d', p);
      m.setAttribute('d', p);
      hl.setAttribute('d', p);
      b.setAttribute('stroke', cB);
      m.setAttribute('stroke', cM);
      hl.setAttribute('stroke', cH);
      b.setAttribute('stroke-width', wB);
      m.setAttribute('stroke-width', wM);
      b.setAttribute('opacity', armOp.toFixed(2));
      m.setAttribute('opacity', armOp.toFixed(2));
      hl.setAttribute('opacity', (armOp * 0.45).toFixed(2));
    }
    for (const [el, j] of [
      [E.elbowL, L.e],
      [E.elbowR, R.e],
    ] as const) {
      el.setAttribute('cx', f1(j.x));
      el.setAttribute('cy', f1(j.y));
      el.setAttribute('opacity', (0.85 * (1 - hoc) * armOp).toFixed(2));
    }

    const eL = pr > 0.5 ? { x: L.h.x, y: L.h.y + 30 } : L.e;
    const eR = pr > 0.5 ? { x: R.h.x, y: R.h.y + 30 } : R.e;
    drawHand(E.hL, 'L', eL, L.h, v('wristL'));
    drawHand(E.hR, 'R', eR, R.h, v('wristR'));

    // lens in whichever fist holds it
    E.lens.setAttribute('opacity', lvis.toFixed(2));
    E.lens.setAttribute('transform', `translate(${f1(lh.x)} ${f1(lh.y - 6)}) scale(${(lsc * lmir).toFixed(2)} ${lsc.toFixed(2)})`);
    E.lensFog.setAttribute('opacity', (op('fog') * 0.6).toFixed(2));
    E.scan.setAttribute('transform', `translate(0 ${f1(Math.sin(t * 3.2) * 20)})`);
    E.hud.setAttribute('transform', `rotate(${f1((t * 90) % 360)})`);

    // props
    const bg = op('burger');
    E.burger.setAttribute('opacity', clamp(bg * 1.4, 0, 1).toFixed(2));
    E.burger.setAttribute('transform', `translate(${f1(R.h.x - 4)} ${f1(R.h.y - 22)}) scale(${(0.6 + bg * 0.6).toFixed(2)})`);
    const it = idleAct === 'snack' ? now - idleT : 0;
    const biteR = (a: number) => (it > a ? clamp((it - a) / 0.08, 0, 1) * 7.5 : 0);
    E.bites[0].setAttribute('r', f1(biteR(1.05)));
    E.bites[1].setAttribute('r', f1(biteR(1.05)));
    E.bites[2].setAttribute('r', f1(biteR(1.85)));
    E.bites[3].setAttribute('r', f1(biteR(1.85)));

    const jc = op('juice');
    const jx = L.h.x + 2;
    const jy = L.h.y - 8;
    E.juice.setAttribute('opacity', clamp(jc * 1.4, 0, 1).toFixed(2));
    E.juice.setAttribute('transform', `translate(${f1(jx)} ${f1(jy)})`);
    // straw: straight up out of the box, then bends so the tip reaches the mouth
    const mouthX = 150 + v('hx') + ex;
    const mouthY = MOUTH_Y + hdY + ey + 2;
    const near = clamp(1 - (Math.hypot(mouthX - jx, mouthY - jy) - 50) / 30, 0, 1);
    const tipX = lerp(6, clamp(mouthX - jx, -10, 34), near);
    const tipY = lerp(-48, clamp(mouthY - jy, -70, -42), near);
    const strawD = `M4 -32 L4 -40 Q4 ${f1(lerp(-46, tipY + 2, near))} ${f1(tipX)} ${f1(tipY)}`;
    E.straw.setAttribute('d', strawD);
    E.strawStripe.setAttribute('d', strawD);

    const cl = op('cloth');
    E.cloth.setAttribute('opacity', clamp(cl * 1.5, 0, 1).toFixed(2));
    E.cloth.setAttribute('transform', `translate(${f1(R.h.x - 4)} ${f1(R.h.y - 10)}) rotate(${f1(-12 + Math.sin(t * 8) * 8)}) scale(${(0.6 + cl * 0.6).toFixed(2)})`);
    E.pocketCloth.setAttribute('opacity', (1 - cl).toFixed(2));

    // phone in the right fist
    const phv = op('phone');
    E.phone.setAttribute('opacity', clamp(phv * 1.4, 0, 1).toFixed(2));
    const phs = 0.6 + phv * 0.5;
    E.phone.setAttribute('transform', `translate(${f1(R.h.x)} ${f1(R.h.y + 2)}) scale(${phs.toFixed(2)})`);
    const fl = clamp(1 - (now - flashT) / 0.4, 0, 1);
    E.flash.setAttribute('opacity', fl.toFixed(2));
    E.flash.setAttribute('transform', `translate(${f1(R.h.x - 5 * phs)} ${f1(R.h.y + 2 - 40 * phs)}) scale(${(0.6 + (1 - fl) * 0.8).toFixed(2)})`);

    // console between both fists
    const gm = op('game');
    E.console.setAttribute('opacity', clamp(gm * 1.4, 0, 1).toFixed(2));
    E.console.setAttribute('transform', `translate(${f1((L.h.x + R.h.x) / 2)} ${f1((L.h.y + R.h.y) / 2 - 2)}) scale(${(0.7 + gm * 0.45).toFixed(2)})`);
    const winning = idleAct === 'game' && now - idleT > 4.1;
    E.cscreen.setAttribute('fill', winning ? mix('#1F3550', GOLD, 0.5 + Math.sin(t * 16) * 0.5) : '#1F3550');
    E.cship.setAttribute('transform', `translate(${f1(Math.sin(t * 4) * 10)} 0)`);
    E.cfoe.setAttribute('transform', `translate(${f1(Math.sin(t * 2.3 + 1) * 11)} 0)`);
    E.cfoe.setAttribute('opacity', winning ? '0' : (0.6 + Math.sin(t * 12) * 0.4).toFixed(2));
    E.cshot.setAttribute('transform', `translate(${f1(Math.sin(t * 4) * 10)} ${f1(-((t * 40) % 14))})`);

    // high-five burst at the palm
    const fv = now - fiveT;
    const fo = fv < 0.55 ? 1 - fv / 0.55 : 0;
    E.five.setAttribute('opacity', fo.toFixed(2));
    E.five.setAttribute('transform', `translate(${f1(R.h.x)} ${f1(R.h.y - 22)}) scale(${(0.7 + fv * 1.4).toFixed(2)})`);

    // sleep mask + zzz
    const mk = v('mask');
    E.mask.setAttribute('opacity', clamp(mk * 1.4, 0, 1).toFixed(2));
    E.mask.setAttribute('transform', `translate(0 ${f1((1 - mk) * -60)}) rotate(${f1((1 - mk) * -18)} 150 120)`);
    const nz = op('nap');
    E.zzz.setAttribute('opacity', nz.toFixed(2));
    for (let i = 0; i < 3; i++) {
      const phz = (t * 0.35 + i / 3) % 1;
      E.z[i].setAttribute('x', f1(214 + v('hx') + phz * 34 + Math.sin(t * 2 + i) * 4));
      E.z[i].setAttribute('y', f1(70 + hdY - phz * 52));
      E.z[i].setAttribute('opacity', Math.sin(phz * Math.PI).toFixed(2));
    }

    // skateboard, wheels, dust
    const bd = op('board');
    let bx = 0;
    let brot = 0;
    if (state === 'skate') {
      const ts = now - stateT;
      if (ts > 1.75) {
        bx = (ts - 1.75) * 280;
        brot = (ts - 1.75) * 30;
      }
    }
    E.board.setAttribute('opacity', (state === 'skate' ? clamp(1 - (bx - 120) / 80, 0, 1) : bd).toFixed(2));
    E.board.setAttribute('transform', `translate(${f1(bx)} 0) rotate(${f1(brot)} 150 320)`);
    const spin = state === 'skate' ? (now - stateT) * 900 * Math.max(0.15, 1 - (now - stateT) / 1.35) : 0;
    E.wheels[0].setAttribute('transform', `translate(100 330) rotate(${f1(spin)})`);
    E.wheels[1].setAttribute('transform', `translate(200 330) rotate(${f1(spin)})`);
    const dt0 = state === 'skate' ? now - stateT - 1.15 : -1;
    const dOp = dt0 > 0 && dt0 < 0.8 ? Math.sin((dt0 / 0.8) * Math.PI) * 0.8 : 0;
    E.dust.setAttribute('opacity', dOp.toFixed(2));
    for (let i = 0; i < 3; i++) {
      E.d[i].setAttribute('cx', f1(skx + 90 - dt0 * (40 + i * 22)));
      E.d[i].setAttribute('cy', f1(326 - dt0 * (10 + i * 6)));
    }

    const pf = op('puff');
    E.puff.setAttribute('opacity', (pf * 0.6).toFixed(2));
    E.puff.setAttribute('transform', `translate(152 ${f1(196 + v('hy') - (1 - pf) * 6)}) scale(${(0.4 + pf * 0.6).toFixed(2)})`);

    const nt = op('notes');
    E.notes.setAttribute('opacity', nt.toFixed(2));
    for (let i = 0; i < 4; i++) {
      const phz = (t * 0.42 + i / 4) % 1;
      const left = i % 2 === 0;
      const x = (left ? 30 : 270) + v('hx') + (left ? -1 : 1) * phz * 20 + Math.sin(t * 3 + i) * 6;
      const y = 120 + hdY - phz * 90;
      E.nt[i].setAttribute(
        'transform',
        `translate(${f1(x)} ${f1(y)}) rotate(${f1(Math.sin(t * 4 + i) * 16)}) scale(${(0.9 + 0.3 * Math.sin(phz * Math.PI)).toFixed(2)})`,
      );
      E.nt[i].setAttribute('opacity', Math.sin(phz * Math.PI).toFixed(2));
    }

    E.led.setAttribute('opacity', (0.6 + Math.sin(t * 4) * 0.4).toFixed(2));

    const sp = op('sparkle');
    E.sparks.setAttribute('opacity', sp.toFixed(2));
    const pos = [[272, 112], [278, 168], [232, 40], [30, 76]];
    for (let i = 0; i < 4; i++) {
      const sc = sp * (0.7 + 0.4 * Math.sin(t * 6 + i * 2.1)) * (i > 1 ? 0.85 : 1.15);
      E.sp[i].setAttribute(
        'transform',
        `translate(${pos[i][0]} ${pos[i][1]}) rotate(${f1(Math.sin(t * 2 + i) * 14)}) scale(${Math.max(0.01, sc).toFixed(2)})`,
      );
    }
  }

  function frame(ms: number) {
    raf = requestAnimationFrame(frame);
    const t = ms / 1000;
    const dt = clamp(t - last, 0, 1 / 20);
    last = t;
    now = t;

    if (endAt > 0 && now > endAt) {
      const done = state;
      state = 'idle';
      stateT = now;
      endAt = -1;
      scheduleIdle();
      opts.onSettle?.(done);
    }
    if (napAfter && state === 'idle' && !idleAct && !napping && !hovered && !intro.length && now - lastActive > napAfter) startNap();
    if (state === 'idle' && !idleAct && !hovered && !napping && now - wakeT > 1.3 && now > nextIdle) {
      const a = pickIdle();
      if (a) startIdle(a);
      else scheduleIdle();
    }

    const ts = now - stateT;
    stepSprings(dt, targets(ts, now));
    render(now);

    const text = bubbleFor(ts);
    if (text) renderText(text);
    bubbleEl.classList.toggle('on', !!text);
  }

  const t0 = performance.now() / 1000;
  now = t0;
  last = t0;
  stateT = t0;
  nextBlink = t0 + 1.6;
  lastActive = t0;
  scheduleIdle(true);
  if (opts.state && ONE_SHOT[opts.state] && oneShot) endAt = t0 + ONE_SHOT[opts.state]!;
  raf = requestAnimationFrame(frame);

  return {
    setState,
    wave: () => setState('wave'),
    playIdle(a) {
      if (state !== 'idle' && a !== 'wave') setState('idle');
      startIdle(a);
    },
    poke,
    nap() {
      if (state !== 'idle') setState('idle');
      startNap();
    },
    wake,
    setLookTarget(p) {
      lookTarget = p;
    },
    say(text, ms = 2500) {
      sayText = text;
      sayUntil = now + ms / 1000;
    },
    destroy() {
      cancelAnimationFrame(raf);
      clearTimeout(touchTimer);
      window.removeEventListener('pointermove', onMove);
      container.removeEventListener('pointerenter', onEnter);
      container.removeEventListener('pointerleave', onLeave);
      container.removeEventListener('pointerdown', onDown);
      svg.remove();
      bubbleEl.remove();
    },
  };
}

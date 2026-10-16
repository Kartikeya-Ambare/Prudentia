/**
 * Prudie colour tokens, built the same way as the Prudentia app (PNS + 2 tiers).
 *
 *  P  Personality: indigo (the app's brand, #5B62D4 is its dark-theme primary). One accent, locked.
 *  N  Neutrals:    the app's graphite scale. No pure black, no pure white on the body.
 *  S  Signal:      mint (CopilotKit's #5FDAA5) = "alive / OK": eyes, HUD, status LEDs.
 *                  Coral = blush and hearts, amber = sparkles and the win flash.
 *
 * Tier 1 = primitives (what the colour IS). Tier 2 = semantic aliases (what it is FOR).
 * The engine only reads tier 2, so re-theming Prudie means editing this file, nothing else.
 * Primitives 50-900 are copied from the app's src/index.css so the mascot cannot drift from the UI.
 */

/* ───────────── tier 1: primitives ───────────── */
export const indigo = {
  50: '#EEEFFA', 100: '#D9DEF4', 200: '#BCC5EA', 300: '#9AA7DD', 400: '#7482C0',
  500: '#5B62D4', 600: '#4E65B5', 700: '#3D50A8', 800: '#2C3A6E', 900: '#1C2548',
} as const;

export const graphite = {
  50: '#E2E2E3', 100: '#BCBCBE', 200: '#A6A6A8', 300: '#8F8F92', 400: '#77777B',
  500: '#56565A', 600: '#36353B', 700: '#313036', 800: '#2A2930', 900: '#212026', 950: '#15141B',
} as const;

export const mint = {
  50: '#EFFFF8', 100: '#D6FBEA', 200: '#A8F0D2', 300: '#5FDAA5', 400: '#3FBF8B', 500: '#2F9F78',
} as const;

export const coral = { 200: '#F4B8AE', 300: '#F0A39A', 400: '#E98C80' } as const;
export const amber = { 200: '#F2CF74', 300: '#F0C36B', 400: '#D4A03A' } as const;
export const frost = { 50: '#F4F5FB', 100: '#E4E5F0', 200: '#CDCFDF', 300: '#B0B3C8', 400: '#8E92AB' } as const;

/* ───────────── tier 2: semantic ───────────── */
export const T = {
  shell: indigo[500], shellHi: indigo[300], shellLo: indigo[700], shellDeep: indigo[900],
  screenTop: graphite[800], screenBot: graphite[950],
  eye: mint[50], eyeGlow: mint[300],
  hud: mint[300], hudSoft: mint[200],
  blush: coral[300], heart: coral[300],
  spark: amber[300],
  glove: graphite[600], gloveHi: graphite[500], gloveLo: graphite[950],
  hood: graphite[300], hoodHi: graphite[100], hoodLo: graphite[500],
  drawstring: coral[200],
  pad: indigo[200],
  cloth: mint[100], clothLo: mint[300],
  silver: frost[50], silverMid: frost[200], silverLo: frost[300], silverDeep: frost[400],
  shadow: graphite[950],
  earLed: mint[300],
} as const;

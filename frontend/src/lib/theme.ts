import { create } from "zustand";

export type Theme = "light" | "dark";

const STORAGE_KEY = "prudentia-theme";
/** Match --color-page so the browser chrome follows the theme. */
const CHROME_COLOR: Record<Theme, string> = { light: "#f8f7f4", dark: "#15141b" };

function readStored(): Theme {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light"; // storage blocked: fall back to the default
  }
}

function paint(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", CHROME_COLOR[theme]);
}

interface ThemeState {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

/** Light is the default. A saved choice wins; the system setting is not followed. */
export const useTheme = create<ThemeState>()((set) => ({
  theme: readStored(),
  setTheme: (theme) => {
    paint(theme);
    try {
      localStorage.setItem(STORAGE_KEY, theme);
    } catch {
      /* private mode: the choice just won't persist */
    }
    set({ theme });
  },
}));

paint(useTheme.getState().theme);

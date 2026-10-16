import { MoonIcon, SunIcon } from "@phosphor-icons/react";
import { useTheme } from "@/lib/theme";

/**
 * Light/dark switch, matching the one in the DASCA navbar: a rounded square
 * button with a softly tinted background, a moon in light mode and a sun in
 * dark mode, growing slightly on hover. The visible button is 40px; a
 * pseudo-element extends the tap area to 48px.
 */
export function ThemeToggle() {
  const { theme, setTheme } = useTheme();
  const next = theme === "light" ? "dark" : "light";

  return (
    <button
      type="button"
      onClick={() => setTheme(next)}
      aria-label="Toggle dark mode"
      aria-pressed={theme === "dark"}
      className="theme-toggle relative shrink-0 rounded-lg p-2 text-ink before:absolute before:-inset-1.5 before:content-['']"
    >
      <span key={theme} className="icon-swap inline-flex">{theme === "light" ? <MoonIcon size={20} aria-hidden /> : <SunIcon size={20} aria-hidden />}</span>
    </button>
  );
}

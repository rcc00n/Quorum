"use client";
import { useEffect, useState } from "react";

// DECISION(2026-10-26, Anastasia/Claude Code): the theme is a per-viewer convenience kept in localStorage
// ("quorum-theme": "light" | "dark") and applied as data-theme on <html>; app/layout.tsx applies the stored
// value before first paint, so a dark choice does not flash light. Light is the default; nothing reads
// prefers-color-scheme yet (the app routes have no dark theme). Why: Anastasia asked for the light landing
// to continue into sign-up, with dark as a switch rather than a jump.
export const THEME_KEY = "quorum-theme";

export function ThemeToggle() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    setDark(document.documentElement.dataset.theme === "dark");
  }, []);
  function toggle() {
    const next = !dark;
    setDark(next);
    const root = document.documentElement;
    // The switch is atomic: transitions are off for one frame so no element keeps the old theme's colour.
    root.classList.add("theme-switching");
    root.dataset.theme = next ? "dark" : "light";
    window.setTimeout(() => root.classList.remove("theme-switching"), 250);
    try {
      localStorage.setItem(THEME_KEY, next ? "dark" : "light");
    } catch {
      /* private mode or blocked storage: the choice lasts for this page only */
    }
  }
  return (
    <button type="button" className="theme-toggle" aria-pressed={dark} onClick={toggle} aria-label={dark ? "Switch to the light theme" : "Switch to the dark theme"}>
      {dark ? "Light" : "Dark"}
    </button>
  );
}

"use client";

import { useTheme } from "@/components/ThemeProvider";

export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, toggleTheme } = useTheme();
  const nextLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return <button type="button" onClick={toggleTheme} className={`theme-toggle ${compact ? "theme-toggle-compact" : ""}`} aria-label={nextLabel} title={nextLabel}>
    <span aria-hidden="true" className="theme-toggle-icon">{theme === "dark" ? "☀" : "☾"}</span>
    {!compact && <span>{theme === "dark" ? "Light mode" : "Dark mode"}</span>}
  </button>;
}

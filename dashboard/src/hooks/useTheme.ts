import { useCallback } from "react";
import { useLocalStorage } from "./useLocalStorage";

export type Theme = "dark" | "light";

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useLocalStorage<Theme>("recall_theme", "dark");

  const toggle = useCallback(() => {
    const next = theme === "dark" ? "light" : "dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
  }, [theme, setTheme]);

  return { theme, toggle };
}

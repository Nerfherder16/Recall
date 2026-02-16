import { useCallback } from "react";
import { useLocalStorage } from "./useLocalStorage";

export type Theme = "recall-dark" | "recall-light";

export function useTheme(): { theme: Theme; toggle: () => void } {
  const [theme, setTheme] = useLocalStorage<Theme>("recall_theme", "recall-dark");

  const toggle = useCallback(() => {
    const next = theme === "recall-dark" ? "recall-light" : "recall-dark";
    setTheme(next);
    document.documentElement.setAttribute("data-theme", next);
  }, [theme, setTheme]);

  return { theme, toggle };
}

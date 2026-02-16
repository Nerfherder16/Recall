import { createContext, useContext } from "react";
import { useTheme, type Theme } from "../hooks/useTheme";

interface ThemeCtx {
  theme: Theme;
  toggle: () => void;
}

const Ctx = createContext<ThemeCtx>({ theme: "recall-dark", toggle: () => {} });

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const value = useTheme();
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useThemeContext() {
  return useContext(Ctx);
}

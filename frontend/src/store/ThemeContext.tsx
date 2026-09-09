import React, { createContext, useContext, useEffect, useState } from "react";
import type { ThemeConfig } from "antd";
import { LIGHT_THEME, DARK_THEME } from "../styles/theme";

export type ThemeMode = "light" | "dark";

interface ThemeContextValue {
  mode: ThemeMode;
  theme: ThemeConfig;
  toggle: () => void;
  setMode: (m: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeContextValue>({
  mode: "light",
  theme: LIGHT_THEME,
  toggle: () => {},
  setMode: () => {},
});

const STORAGE_KEY = "aipm-theme";

export const ThemeProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = (typeof localStorage !== "undefined" && localStorage.getItem(STORAGE_KEY)) as ThemeMode | null;
    return saved === "dark" || saved === "light" ? saved : "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.dataset.theme = mode;
    root.style.colorScheme = mode;
    try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* ignore */ }
  }, [mode]);

  const toggle = () => setMode((m) => (m === "light" ? "dark" : "light"));

  const theme = mode === "dark" ? DARK_THEME : LIGHT_THEME;

  return (
    <ThemeContext.Provider value={{ mode, theme, toggle, setMode }}>
      {children}
    </ThemeContext.Provider>
  );
};

export const useTheme = (): ThemeContextValue => useContext(ThemeContext);

import { create } from "zustand";
import { getJson, postJson } from "../lib/api";

interface ThemeState {
  theme: "light" | "dark";
  toggleTheme: () => void;
  fetchTheme: () => void;
}

const useThemeStore = create<ThemeState>((set, get) => ({
  theme: "light",
  toggleTheme: () => {
    const current = get().theme;
    const newTheme = current === "light" ? "dark" : "light";
    set({ theme: newTheme });
    // Persist user preference to backend
    postJson("/settings/theme", { theme: newTheme }).catch((err) => {
      console.error("Failed to update theme preference", err);
    });
  },
  fetchTheme: () => {
    getJson<{ theme: string }>("/settings/theme")
      .then((data) => {
        if (data && (data.theme === "light" || data.theme === "dark")) {
          set({ theme: data.theme });
        }
      })
      .catch((err) => {
        console.error("Failed to load theme preference", err);
      });
  },
}));

export default useThemeStore;

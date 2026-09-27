export const THEME_STORAGE_KEY = "vigie-theme";

export type ThemeChoice = "light" | "dark";

export const themeBootScript = `(function(){try{var stored=localStorage.getItem("${THEME_STORAGE_KEY}");if(stored==="light"){document.documentElement.removeAttribute("data-theme")}else{document.documentElement.setAttribute("data-theme","dark")}}catch(e){document.documentElement.setAttribute("data-theme","dark")}})();`;

export function readTheme(): ThemeChoice {
  if (typeof document === "undefined") {
    return "dark";
  }
  return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
}

export function applyTheme(theme: ThemeChoice): void {
  if (theme === "dark") {
    document.documentElement.setAttribute("data-theme", "dark");
  } else {
    document.documentElement.removeAttribute("data-theme");
  }
  localStorage.setItem(THEME_STORAGE_KEY, theme);
}

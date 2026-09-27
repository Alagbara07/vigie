/// <reference types="vitest/globals" />
import { THEME_STORAGE_KEY, themeBootScript } from "@/lib/theme";

function runBootScript(): void {
  new Function(themeBootScript)();
}

describe("theme boot", () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.setAttribute("data-theme", "dark");
  });

  it("keeps dark mode on a first visit and ignores the system theme", () => {
    const matchMedia = vi.fn(() => ({ matches: false }));
    vi.stubGlobal("matchMedia", matchMedia);

    runBootScript();

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
    expect(matchMedia).not.toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it("removes dark mode only when the visitor chose light", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "light");

    runBootScript();

    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });

  it("keeps a stored dark choice", () => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    document.documentElement.removeAttribute("data-theme");

    runBootScript();

    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});

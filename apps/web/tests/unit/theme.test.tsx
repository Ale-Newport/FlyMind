import { afterEach, describe, expect, it } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { chartColors, categoryColor, hashColor, hexToRgb, rateColor } from "../../src/lib/colors";
import { THEME_STORAGE_KEY, useTheme, useThemeStore } from "../../src/lib/theme";
import { ThemeToggle } from "../../src/components/ThemeToggle";

// WCAG relative luminance / contrast helpers
const lin = (v: number) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4);
const lum = (hex: string) => { const [r, g, b] = hexToRgb(hex); return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b); };
const contrast = (a: string, b: string) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

afterEach(() => {
  window.localStorage.clear();
  act(() => useThemeStore.setState({ pref: "system", system: "dark" }));
});

describe("theme state", () => {
  it("resolves 'system' from the OS setting and explicit prefs over it", () => {
    act(() => useThemeStore.setState({ pref: "system", system: "light" }));
    const { result } = renderHook(() => useTheme());
    expect(result.current.resolved).toBe("light");
    act(() => result.current.setPref("dark"));
    expect(result.current.resolved).toBe("dark");
    expect(result.current.pref).toBe("dark");
  });
  it("persists the preference and applies it to <html data-theme>", () => {
    const { result } = renderHook(() => useTheme());
    act(() => result.current.setPref("light"));
    expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");
    expect(document.documentElement.dataset.theme).toBe("light");
    act(() => result.current.setPref("dark"));
    expect(document.documentElement.dataset.theme).toBe("dark");
  });
  it("toggle exposes pressed state and switches the theme", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "System theme" }).getAttribute("aria-pressed")).toBe("true");
    act(() => screen.getByRole("button", { name: "Light theme" }).click());
    expect(screen.getByRole("button", { name: "Light theme" }).getAttribute("aria-pressed")).toBe("true");
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});

describe("theme-aware colours", () => {
  it("keeps the dark defaults unchanged", () => {
    expect(categoryColor("nt_type", "GABA", "dark")).toBe("#f43f5e");
    expect(hashColor("AL_L", "dark")).toBe(hashColor("AL_L"));
  });
  it("light categorical colours are visible on a white background", () => {
    for (const label of ["ACH", "GABA", "GLUT", "DA", "SER", "OCT", "HIST"]) expect(contrast(categoryColor("nt_type", label, "light"), "#ffffff")).toBeGreaterThan(3);
    for (let i = 0; i < 200; i++) expect(contrast(hashColor(`label-${i}`, "light"), "#ffffff")).toBeGreaterThan(2.4);
  });
  it("accent passes AA on both surfaces", () => {
    const d = chartColors("dark"), l = chartColors("light");
    expect(contrast(d.accent, d.scene.bg)).toBeGreaterThan(7);
    expect(contrast(l.accent, "#ffffff")).toBeGreaterThan(4.5);
    expect(contrast(l.text, "#ffffff")).toBeGreaterThan(7);
    expect(l.scene.additiveOk).toBe(false);
  });
  it("light rate ramp gets darker with rate (salient on light backgrounds)", () => {
    const sum = (c: number[]) => c[0] + c[1] + c[2];
    expect(sum(rateColor(1, "light"))).toBeLessThan(sum(rateColor(0.5, "light")));
    expect(sum(rateColor(0.5, "light"))).toBeLessThan(sum(rateColor(0, "light")));
  });
});

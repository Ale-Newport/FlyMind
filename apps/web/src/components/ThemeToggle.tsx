import { type ThemePref, useTheme } from "../lib/theme";

const ICON = { width: 14, height: 14, viewBox: "0 0 16 16", fill: "none", stroke: "currentColor", strokeWidth: 1.5, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;

const OPTIONS: { value: ThemePref; label: string; icon: React.ReactNode }[] = [
  { value: "system", label: "System", icon: <svg {...ICON}><rect x="2" y="3" width="12" height="8.5" rx="1.5" /><path d="M5.5 14h5M8 11.5V14" /></svg> },
  { value: "light", label: "Light", icon: <svg {...ICON}><circle cx="8" cy="8" r="2.8" /><path d="M8 1.8v1.4M8 12.8v1.4M1.8 8h1.4M12.8 8h1.4M3.6 3.6l1 1M11.4 11.4l1 1M3.6 12.4l1-1M11.4 4.6l1-1" /></svg> },
  { value: "dark", label: "Dark", icon: <svg {...ICON}><path d="M13.2 9.6A5.6 5.6 0 0 1 6.4 2.8a5.6 5.6 0 1 0 6.8 6.8Z" /></svg> },
];

/** System / light / dark segmented control. Persisted via src/lib/theme.ts. */
export function ThemeToggle() {
  const { pref, setPref } = useTheme();
  return (
    <div className="seg" role="group" aria-label="Colour theme">
      {OPTIONS.map((o, i) => (
        <button key={o.value} type="button" aria-pressed={pref === o.value} aria-label={`${o.label} theme`}
          data-tip={`${o.label} theme`} data-tip-align={i === OPTIONS.length - 1 ? "end" : undefined}
          className="btn !px-1.5 !py-1" onClick={() => setPref(o.value)}>
          {o.icon}
        </button>
      ))}
    </div>
  );
}

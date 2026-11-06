import { type ThemePref, useTheme } from "../lib/theme";
import { Icon, type IconName } from "./Icon";

const OPTIONS: { value: ThemePref; label: string; icon: IconName }[] = [
  { value: "system", label: "System", icon: "monitor" },
  { value: "light", label: "Light", icon: "sun" },
  { value: "dark", label: "Dark", icon: "moon" },
];

/** System / light / dark switch. Persisted via src/lib/theme.ts. */
export function ThemeToggle() {
  const { pref, setPref } = useTheme();
  return (
    <div className="seg" role="group" aria-label="Colour theme">
      {OPTIONS.map((o, i) => (
        <button key={o.value} type="button" aria-pressed={pref === o.value} aria-label={`${o.label} theme`}
          data-tip={`${o.label} theme`} data-tip-align={i === OPTIONS.length - 1 ? "end" : undefined}
          style={{ width: 28, padding: 0 }} onClick={() => setPref(o.value)}>
          <Icon name={o.icon} size={14} />
        </button>
      ))}
    </div>
  );
}

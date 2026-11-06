import type { SVGProps } from "react";

/**
 * FlyMind icon set. Drawn on a 16px grid with a 1.5px stroke, square caps and mitred joins (curves are
 * circular arcs), so the glyphs sit on the same pixel grid as the hairline rules and read as one family
 * with the type. All icons inherit `currentColor`.
 */
const P = {
  play: <path d="M4.5 2.75 12.5 8l-8 5.25Z" />,
  pause: <path d="M5.25 3.75v8.5M10.75 3.75v8.5" />,
  stop: <rect x="3.75" y="3.75" width="8.5" height="8.5" />,
  step: <path d="M3.75 3.75 10 8l-6.25 4.25ZM12.5 3.5v9" />,
  reset: <path d="M3.4 9.6a5.2 5.2 0 1 0 1.3-5.5L2.2 6.4M2.2 2.4v4h4" />,
  follow: <><path d="M2.75 6V2.75H6M10 2.75h3.25V6M13.25 10v3.25H10M6 13.25H2.75V10" /><circle cx="8" cy="8" r="1.25" /></>,
  orbit: <><ellipse cx="8" cy="8" rx="6" ry="2.75" transform="rotate(-28 8 8)" /><circle cx="8" cy="8" r="1" /></>,
  crosshair: <><circle cx="8" cy="8" r="3.75" /><path d="M8 1.75v3M8 11.25v3M1.75 8h3M11.25 8h3" /></>,
  save: <path d="M3.25 2.75h7.1l2.4 2.4v8.1h-9.5ZM5.75 2.75v3.5h4.5M5.5 13.25v-4.5h5v4.5" />,
  refresh: <path d="M13 8a5 5 0 0 1-8.7 3.35M3 8a5 5 0 0 1 8.7-3.35M12.1 1.9v2.9H9.2M3.9 14.1v-2.9h2.9" />,
  info: <><circle cx="8" cy="8" r="5.75" /><path d="M8 7.25v3.75M8 4.9v.2" /></>,
  close: <path d="m3.75 3.75 8.5 8.5m0-8.5-8.5 8.5" />,
  "chevron-down": <path d="m3.75 6 4.25 4.25L12.25 6" />,
  "chevron-up": <path d="m3.75 10 4.25-4.25L12.25 10" />,
  "chevron-right": <path d="m6 3.75 4.25 4.25L6 12.25" />,
  sun: <><circle cx="8" cy="8" r="2.75" /><path d="M8 1.75v1.5M8 12.75v1.5M1.75 8h1.5M12.75 8h1.5M3.6 3.6l1.05 1.05M11.35 11.35l1.05 1.05M3.6 12.4l1.05-1.05M11.35 4.65l1.05-1.05" /></>,
  moon: <path d="M12.75 9.6A5.4 5.4 0 0 1 6.4 3.25a5.4 5.4 0 1 0 6.35 6.35Z" />,
  monitor: <><rect x="2.25" y="3" width="11.5" height="7.5" /><path d="M5.75 13.25h4.5M8 10.5v2.75" /></>,
  search: <><circle cx="7" cy="7" r="4.25" /><path d="m10.25 10.25 3.5 3.5" /></>,
  plus: <path d="M8 3v10M3 8h10" />,
  minus: <path d="M3 8h10" />,
  download: <path d="M8 2.5v7.5M4.75 7.25 8 10.5l3.25-3.25M3 13.25h10" />,
  external: <path d="M9.25 2.75h4v4M13.25 2.75l-6 6M11.25 9.5v3.75h-8.5v-8.5h3.75" />,
  "arrow-right": <path d="M2.75 8h10.5M9 3.75 13.25 8 9 12.25" />,
  check: <path d="m3 8.5 3.25 3.25L13 4.5" />,
  fly: <><ellipse cx="4.5" cy="6" rx="3.5" ry="1.6" transform="rotate(-32 4.5 6)" /><ellipse cx="11.5" cy="6" rx="3.5" ry="1.6" transform="rotate(32 11.5 6)" /><ellipse cx="8" cy="10" rx="1.4" ry="3.6" /><path d="M8 5.2v.01" /></>,
  walk: <><ellipse cx="8" cy="8" rx="1.75" ry="3.5" /><path d="M6.3 6.4 3 4.5M6.25 8H2.5M6.3 9.6 3 11.5M9.7 6.4 13 4.5M9.75 8h3.75M9.7 9.6l3.3 1.9" /></>,
  keyboard: <><rect x="1.75" y="4" width="12.5" height="8" /><path d="M4.5 7h.01M7 7h.01M9.5 7h.01M12 7h.01M5 9.75h6" /></>,
} as const;

export type IconName = keyof typeof P;
export const ICON_NAMES = Object.keys(P) as IconName[];

export function Icon({ name, size = 16, className, ...rest }: { name: IconName; size?: number } & Omit<SVGProps<SVGSVGElement>, "name">) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 16 16" fill="none" stroke="currentColor"
      strokeWidth={1.5} strokeLinecap="square" strokeLinejoin="miter" aria-hidden focusable="false" className={className} {...rest}
    >
      {P[name]}
    </svg>
  );
}

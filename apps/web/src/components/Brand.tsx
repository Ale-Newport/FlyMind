import { NavLink } from "react-router-dom";

/**
 * The FlyMind mark: a Drosophila wing, drawn from its venation. The outline and two veins are the
 * ink; the third longitudinal vein (L3) carries the accent, the one line that "has the signal".
 */
export function Mark({ size = 24, className }: { size?: number; className?: string }) {
  // the wing figure's geometry, scaled into a 26 x 14.5 box; strokes stay constant in screen pixels
  const common = { fill: "none", vectorEffect: "non-scaling-stroke" as const, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg width={(size * 27) / 14.5} height={size} viewBox="0 0 27 14.5" aria-hidden className={className}>
      <g transform="translate(-1.84 -2.1) scale(0.0395)">
        <path d="M72 300C110 250 230 170 380 140C490 118 600 104 648 124C700 146 702 210 654 256C600 308 500 340 380 352C290 361 200 358 150 346C118 338 92 322 72 300Z" stroke="currentColor" strokeWidth={1.3} {...common} />
        <path d="M72 300C110 250 230 170 380 140C490 118 600 104 648 124" stroke="currentColor" strokeWidth={2} {...common} />
        <path d="M102 298C165 262 275 214 395 190C500 170 600 152 676 148" stroke="currentColor" strokeWidth={0.9} {...common} />
        <path d="M104 300C180 278 300 244 420 224C520 208 610 196 688 181" stroke="var(--accent)" strokeWidth={1.7} {...common} />
        <path d="M106 302C190 292 320 270 440 256C540 245 630 232 681 219" stroke="currentColor" strokeWidth={0.9} {...common} />
        <path d="M108 304C210 318 340 322 460 316C530 312 575 302 605 291" stroke="currentColor" strokeWidth={0.9} {...common} />
      </g>
    </svg>
  );
}

export function Wordmark({ className = "" }: { className?: string }) {
  return (
    <span className={`font-serif text-[22px] leading-none tracking-[-0.018em] ${className}`} style={{ fontWeight: 540, fontVariationSettings: '"opsz" 30' }}>
      FlyMind
    </span>
  );
}

export function Brand() {
  return (
    <NavLink to="/" aria-label="FlyMind home" className="-ml-1 flex items-center gap-2 px-1 py-2 text-ink no-underline hover:text-ink">
      <Mark size={17} />
      <Wordmark />
    </NavLink>
  );
}

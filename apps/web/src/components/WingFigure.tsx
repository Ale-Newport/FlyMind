import { useMemo } from "react";

/**
 * Overview illustration: a Drosophila wing and its venation, drawn as a schematic plate.
 * Longitudinal veins L1 to L5, the anterior and posterior cross-veins, margin bristles and a few
 * construction arcs from the hinge. Line weights taper from hinge to margin. The third longitudinal
 * vein carries the accent. Everything uses theme variables, so it follows light and dark.
 * It is a drawing for this interface, not data.
 */

type Pt = [number, number];
const bez = (p: [Pt, Pt, Pt, Pt], t: number): Pt => {
  const u = 1 - t;
  return [
    u * u * u * p[0][0] + 3 * u * u * t * p[1][0] + 3 * u * t * t * p[2][0] + t * t * t * p[3][0],
    u * u * u * p[0][1] + 3 * u * u * t * p[1][1] + 3 * u * t * t * p[2][1] + t * t * t * p[3][1],
  ];
};
const tangent = (p: [Pt, Pt, Pt, Pt], t: number): Pt => {
  const e = 0.002;
  const a = bez(p, Math.max(0, t - e)), b = bez(p, Math.min(1, t + e));
  const dx = b[0] - a[0], dy = b[1] - a[1], l = Math.hypot(dx, dy) || 1;
  return [dx / l, dy / l];
};
// deterministic pseudo-random in [0, 1)
const rnd = (i: number) => { const x = Math.sin(i * 127.1 + 311.7) * 43758.5453; return x - Math.floor(x); };

const H: Pt = [72, 300];
const COSTA: [Pt, Pt, Pt, Pt][] = [[H, [110, 250], [230, 170], [380, 140]], [[380, 140], [490, 118], [600, 104], [648, 124]]];
const TIP: [Pt, Pt, Pt, Pt] = [[648, 124], [700, 146], [702, 210], [654, 256]];
const TRAILING: [Pt, Pt, Pt, Pt][] = [[[654, 256], [600, 308], [500, 340], [380, 352]], [[380, 352], [290, 361], [200, 358], [150, 346]]];

const OUTLINE = "M72 300C110 250 230 170 380 140C490 118 600 104 648 124C700 146 702 210 654 256C600 308 500 340 380 352C290 361 200 358 150 346C118 338 92 322 72 300Z";

const VEINS = {
  L1: "M100 296C150 250 270 186 380 162C480 140 580 126 628 122",
  L2: "M102 298C165 262 275 214 395 190C500 170 600 152 676 148",
  L3: "M104 300C180 278 300 244 420 224C520 208 610 196 688 181",
  L4: "M106 302C190 292 320 270 440 256C540 245 630 232 681 219",
  L5: "M108 304C210 318 340 322 460 316C530 312 575 302 605 291",
  A1: "M112 308C190 330 270 342 330 350",
};

const stroke = (color: string, w: number, extra: Record<string, string | number> = {}) => ({ fill: "none", stroke: color, strokeWidth: w, strokeLinecap: "round" as const, ...extra });

/** One vein drawn in three overlaid passes so its weight steps down from hinge to margin. */
function Vein({ d, w, color }: { d: string; w: number; color: string }) {
  return (
    <g>
      <path d={d} {...stroke(color, w * 0.5)} />
      <path d={d} pathLength={100} {...stroke(color, w * 0.8, { strokeDasharray: "62 100" })} />
      <path d={d} pathLength={100} {...stroke(color, w, { strokeDasharray: "26 100" })} />
    </g>
  );
}

export function WingFigure({ className }: { className?: string }) {
  const bristles = useMemo(() => {
    const out: string[] = [];
    const run = (segs: [Pt, Pt, Pt, Pt][], n: number, base: number, spread: number, seed: number) => {
      segs.forEach((seg, si) => {
        for (let k = 0; k < n; k++) {
          const t = (k + 0.5) / n;
          const p = bez(seg, t), tg = tangent(seg, t);
          const nx = tg[1], ny = -tg[0];
          const len = base + rnd(seed + si * 97 + k) * spread;
          const lean = (rnd(seed + si * 31 + k * 3) - 0.5) * 0.35;
          const dx = nx + tg[0] * lean, dy = ny + tg[1] * lean;
          out.push(`M${p[0].toFixed(1)} ${p[1].toFixed(1)}l${(dx * len).toFixed(1)} ${(dy * len).toFixed(1)}`);
        }
      });
    };
    run([TIP], 34, 3.5, 4.5, 3);
    run(TRAILING, 44, 3, 5, 11);
    run(COSTA, 42, 2, 2.6, 23);
    return out.join("");
  }, []);

  const ink = "var(--ink)", ink2 = "var(--ink-2)", ink3 = "var(--ink-3)", rule = "var(--rule-strong)", accent = "var(--accent)";
  const lab = { fill: ink3, fontFamily: "var(--font-mono)", fontSize: 10.5, letterSpacing: 0 } as const;
  const ticks = Array.from({ length: 21 }, (_, i) => 72 + (i * (700 - 72)) / 20);

  return (
    <svg viewBox="0 0 760 440" className={className} role="img" aria-label="Schematic drawing of a Drosophila wing and its veins">
      <title>Drosophila wing venation (schematic)</title>
      {/* construction arcs from the hinge */}
      <g {...stroke(rule, 0.7, { strokeDasharray: "1 5" })}>
        {[150, 270, 390, 510, 630].map((r) => <circle key={r} cx={H[0]} cy={H[1]} r={r} />)}
      </g>
      <g {...stroke(rule, 0.7)}>
        <path d="M72 300H752" strokeDasharray="1 5" />
      </g>

      {/* membrane */}
      <path d={OUTLINE} style={{ fill: "color-mix(in oklab, var(--ink) 4%, transparent)" }} stroke="none" />
      <path d={bristles} {...stroke(ink3, 0.7, { strokeLinecap: "butt" })} />
      <path d={OUTLINE} {...stroke(ink3, 0.9, { strokeLinejoin: "round" })} />

      {/* veins: heavier near the hinge */}
      <path d="M72 300C110 250 230 170 380 140C490 118 600 104 648 124" {...stroke(ink, 2.6)} />
      <Vein d={VEINS.L1} w={2} color={ink} />
      <Vein d={VEINS.L2} w={2} color={ink} />
      <Vein d={VEINS.L3} w={2.8} color={accent} />
      <Vein d={VEINS.L4} w={2} color={ink} />
      <Vein d={VEINS.L5} w={2} color={ink} />
      <path d={VEINS.A1} {...stroke(ink2, 0.9)} />
      {/* cross-veins */}
      <path d="M409 227 415 262" {...stroke(ink, 1.5)} />
      <path d="M522 246 529 307" {...stroke(ink, 1.5)} />

      {/* nodes on the accent vein */}
      <g style={{ fill: accent }}>
        <circle cx="409" cy="227" r="3" />
        <circle cx="688" cy="181" r="3.4" />
      </g>
      <circle cx="104" cy="300" r="6.5" {...stroke(accent, 1)} />
      <circle cx="72" cy="300" r="2.5" style={{ fill: ink }} />

      {/* callouts */}
      <g {...stroke(ink3, 0.7, { strokeLinecap: "butt" })}>
        <path d="M628 122 640 98M676 148l36-7M688 181h26M681 219l33 6M605 291l36 40M72 300l-14 20" />
      </g>
      <g style={lab}>
        <text x="641" y="92">L1</text>
        <text x="718" y="140">L2</text>
        <text x="718" y="185" style={{ fill: accent }}>L3</text>
        <text x="718" y="231">L4</text>
        <text x="645" y="343">L5</text>
        <text x="30" y="334">hinge</text>
        <text x="300" y="128" textAnchor="end">costa</text>
        <text x="424" y="248">acv</text>
        <text x="538" y="282">pcv</text>
        <text x="338" y="366">A1</text>
      </g>

      {/* unlabelled ruler along the foot */}
      <g {...stroke(rule, 0.8, { strokeLinecap: "butt" })}>
        <path d="M72 412H700" />
        {ticks.map((x, i) => <path key={i} d={`M${x.toFixed(1)} 412v${i % 5 === 0 ? 8 : 4}`} />)}
      </g>
    </svg>
  );
}

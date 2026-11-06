import { Icon } from "../components/Icon";
import { Section } from "../components/ui";

const REPO = "https://github.com/Ale-Newport/FlyMind/blob/main/";

const DOCS: { group: string; items: [string, string][] }[] = [
  { group: "Scientific methods", items: [
    ["Neuron model equations and parameters", "docs/scientific/neuron-model.md"],
    ["Connectome sources and licences", "docs/scientific/connectome-sources.md"],
    ["Interventions and what they approximate", "docs/scientific/interventions.md"],
    ["Neural–body interface (bridge)", "docs/scientific/neural-body-interface.md"],
    ["Limitations", "docs/scientific/limitations.md"],
    ["Validation and reproduction", "docs/scientific/validation.md"],
  ] },
  { group: "Architecture", items: [
    ["System overview", "docs/architecture/overview.md"],
    ["Decision records (ADRs)", "docs/architecture/adr/"],
    ["Reference repositories", "docs/research/reference-repositories.md"],
  ] },
  { group: "Tutorials", items: [
    ["Installation", "docs/tutorials/01-installation.md"],
    ["Importing FlyWire data", "docs/tutorials/02-importing-flywire.md"],
    ["Exploring a neuron", "docs/tutorials/03-exploring-a-neuron.md"],
    ["Simulating a small circuit", "docs/tutorials/04-simulating-a-circuit.md"],
    ["Full-brain simulation", "docs/tutorials/05-full-brain.md"],
    ["Activating and silencing neurons", "docs/tutorials/06-activation-silencing.md"],
    ["Running the Virtual fly", "docs/tutorials/07-virtual-fly.md"],
    ["Creating a custom arena", "docs/tutorials/08-custom-arena.md"],
    ["Reproducible experiments", "docs/tutorials/09-reproducible-experiments.md"],
    ["Extending FlyMind", "docs/tutorials/10-extending.md"],
  ] },
  { group: "Evidence", items: [
    ["Feature verification matrix", "docs/evidence/feature-matrix.md"],
    ["Reproduction of Shiu et al. 2024", "docs/evidence/reproduction-shiu2024.md"],
    ["FlyWire v783 experiments", "docs/evidence/flywire783-experiments.md"],
    ["Embodied FlyWire runs", "docs/evidence/embodied-flywire.md"],
    ["Implementation status", "docs/IMPLEMENTATION_STATUS.md"],
    ["Benchmarks", "docs/evidence/benchmarks.md"],
    ["Test results", "docs/evidence/test-results.md"],
  ] },
];

const EQUATIONS = `dv/dt = (v_rest − v + g) / τ_m        (frozen while refractory)
dg/dt = −g / τ_syn                    (frozen while refractory)
v > v_th  →  spike;  v := v_reset, g := 0, refractory for t_ref
presynaptic spike  →  g_post += sign × synapse_count × w_syn   after 1.8 ms
Poisson stimulus spike  →  v += 250 × w_syn  (stimulated neurons have t_ref = 0)`;

export default function Docs() {
  return (
    <div className="mx-auto max-w-[1120px] px-8 pb-24 pt-14">
      <header className="mb-14 max-w-[60ch]">
        <p className="mb-4 text-sm text-ink-3">Reference</p>
        <h1 className="t-title">Documentation</h1>
        <p className="t-lead mt-4 text-ink-2">
          The full documentation lives in the repository and builds with <code>make docs</code>. The equations of the neuron model are summarised here.
        </p>
      </header>

      <Section n="01" title="The model in one paragraph">
        <div className="grid grid-cols-12 gap-x-6 gap-y-6">
          <div className="col-span-12 md:col-span-5">
            <p className="t-body max-w-[48ch] text-ink-2">
              Each neuron is a point leaky integrate-and-fire unit with membrane potential <i>v</i> and synaptic drive <i>g</i>, both in mV.
              Parameters: v_rest = v_reset = −52 mV, v_th = −45 mV, τ_m = 20 ms, τ_syn = 5 ms, t_ref = 2.2 ms, w_syn = 0.275 mV (a free
              parameter), dt = 0.1 ms with exact integration.
            </p>
            <p className="t-body mt-4 max-w-[48ch] text-ink-2">
              FlyMind's Numba engine reproduces Brian2 spike for spike on test networks, and it reproduces the published sugar-GRN to MN9 rates of Shiu et al. (2024).
            </p>
          </div>
          <pre className="mono col-span-12 overflow-x-auto border-l-2 border-ink-4 pl-5 text-xs leading-6 text-ink md:col-span-7" aria-label="Model equations">{EQUATIONS}</pre>
        </div>
      </Section>

      <Section n="02" title="Where to read more" className="mt-20">
        <div className="grid gap-x-12 gap-y-12 md:grid-cols-2">
          {DOCS.map((g) => (
            <div key={g.group}>
              <h3 className="t-head !text-[17px] mb-2">{g.group}</h3>
              <ul className="border-t border-rule-strong">
                {g.items.map(([t, p]) => (
                  <li key={p} className="border-b border-rule">
                    <a className="group grid grid-cols-[1fr_auto] items-baseline gap-x-3 py-2 no-underline" href={REPO + p} target="_blank" rel="noreferrer">
                      <span className="text-sm text-ink group-hover:text-accent">{t}</span>
                      <Icon name="external" size={12} className="relative top-[1px] text-ink-4 group-hover:text-accent" />
                      <span className="sr-only"> (opens in a new tab)</span>
                      <span className="mono col-span-2 truncate text-[11px] text-ink-3">{p}</span>
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </Section>
    </div>
  );
}

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
    ["Running the Virtual Fly", "docs/tutorials/07-virtual-fly.md"],
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

export default function Docs() {
  return (
    <div className="mx-auto max-w-5xl space-y-4 p-6">
      <h1 className="text-xl font-semibold">Documentation</h1>
      <p className="text-sm text-ink-300">The full documentation lives in the repository (and builds with <code className="mono">make docs</code>). Key equations are summarised below.</p>
      <Section title="Model in one paragraph">
        <div className="space-y-2 text-sm text-ink-300">
          <p>Each neuron is a point leaky integrate-and-fire unit with membrane potential <i>v</i> and synaptic drive <i>g</i> (both in mV):</p>
          <pre className="mono overflow-x-auto rounded-lg bg-ink-950 p-3 text-xs text-ink-100">{`dv/dt = (v_rest − v + g) / τ_m        (frozen while refractory)
dg/dt = −g / τ_syn                    (frozen while refractory)
v > v_th  →  spike;  v := v_reset, g := 0, refractory for t_ref
presynaptic spike  →  g_post += sign × synapse_count × w_syn   after 1.8 ms
Poisson stimulus spike  →  v += 250 × w_syn  (stimulated neurons have t_ref = 0)`}</pre>
          <p>v_rest = v_reset = −52 mV, v_th = −45 mV, τ_m = 20 ms, τ_syn = 5 ms, t_ref = 2.2 ms, w_syn = 0.275 mV (a free parameter), dt = 0.1 ms with exact integration. FlyMind's Numba engine reproduces Brian2 spike-for-spike on test networks and reproduces the published sugar-GRN → MN9 rates of Shiu et al. (2024).</p>
        </div>
      </Section>
      <div className="grid gap-4 md:grid-cols-2">
        {DOCS.map((g) => (
          <Section key={g.group} title={g.group}>
            <ul className="space-y-1 text-sm">
              {g.items.map(([t, p]) => <li key={p}><a className="text-accent hover:underline" href={REPO + p} target="_blank" rel="noreferrer">{t}</a> <span className="mono text-[10px] text-ink-400">{p}</span></li>)}
            </ul>
          </Section>
        ))}
      </div>
    </div>
  );
}

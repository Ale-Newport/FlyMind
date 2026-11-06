import { Link } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { useApp } from "../lib/store";
import { EvidenceBadge, Section, fmt, useAsync, useDatasets } from "../components/ui";
import type { Evidence } from "../lib/types";

const MODULES = [
  {
    to: "/explorer", title: "Brain Explorer 3D", shot: "explorer.png", kicker: "Anatomy",
    text: "All 139,255 proofread FlyWire v783 neurons in anatomical space. Search by ID or cell type, inspect inputs and outputs, trace pathways, load reconstructed skeletons and overlay simulated activity.",
  },
  {
    to: "/simulator", title: "Brain Simulator", shot: "simulator.png", kicker: "Dynamics",
    text: "Leaky integrate-and-fire dynamics on the real connectome (Shiu et al. 2024 model), with full-brain, region, circuit and demonstration modes, live stimulation, silencing and reversible lesions.",
  },
  {
    to: "/fly", title: "Virtual Fly", shot: "fly.png", kicker: "Embodiment",
    text: "The official NeuroMechFly body in MuJoCo (FlyGym 2.x). Sensors feed the neural model through a documented interface; descending-neuron activity drives a CPG walking controller.",
  },
];

function Arrow() {
  return (
    <svg aria-hidden width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" className="transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none">
      <path d="M3 8h10M9 4l4 4-4 4" />
    </svg>
  );
}

function StatusRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <li className="flex items-baseline justify-between gap-4 border-b border-ink-800 py-1.5 last:border-b-0">
      <span className="shrink-0 text-ink-400">{label}</span>
      <span className="min-w-0 text-right">{children}</span>
    </li>
  );
}

export default function Overview() {
  const { datasetId } = useApp();
  const ds = useDatasets();
  const sys = useAsync(() => (STATIC_DEMO ? Promise.resolve(null) : api.system()), []);
  const ev = useAsync(() => api.evidence(), []);
  const caps = (sys.data?.capabilities ?? {}) as Record<string, boolean>;
  const fullBrain = ds.data?.find((d) => d.dataset_id === "flywire_fafb_783");
  const active = ds.data?.find((d) => d.dataset_id === datasetId) ?? ds.data?.[0];
  return (
    <div className="mx-auto max-w-6xl space-y-12 px-6 py-10">
      <section aria-labelledby="hero-title" className="max-w-3xl">
        <p className="eyebrow mb-3">Virtual Drosophila laboratory</p>
        <h1 id="hero-title" className="text-3xl font-semibold leading-[1.15] tracking-tight text-ink-100 md:text-[2.5rem]">
          Simulate, embody and explore the fruit-fly connectome.
        </h1>
        <p className="mt-4 max-w-2xl text-[15px] leading-relaxed text-ink-300">
          FlyMind connects the FlyWire whole-brain wiring diagram of an adult female <i>Drosophila melanogaster</i> to a
          reproducible spiking-network model, a physics-based body and an interactive 3D anatomy viewer, and keeps the
          difference between reconstructed data, model assumptions and simulation output visible throughout.
        </p>
        <div className="mt-6 flex flex-wrap gap-2">
          <Link to="/explorer" className="btn btn-primary px-4 py-2">Open the Brain Explorer</Link>
          <Link to="/experiments" className="btn px-4 py-2">Run an experiment</Link>
          <Link to="/docs" className="btn px-4 py-2">Read the methods</Link>
        </div>
      </section>

      {active && (
        <dl className="panel grid grid-cols-2 overflow-hidden md:grid-cols-4">
          {[
            ["Active dataset", active.synthetic ? "Synthetic fixture" : `${active.name} v${active.version}`],
            ["Neurons", fmt.int(active.n_neurons)],
            ["Connections", fmt.int(active.n_edges)],
            ["Synapses", fmt.int(active.n_synapses)],
          ].map(([k, v]) => (
            <div key={k} className="border-ink-700 px-4 py-3 [&:nth-child(n+3)]:border-t md:[&:nth-child(n+3)]:border-t-0 md:[&:not(:first-child)]:border-l [&:nth-child(even)]:border-l">
              <dt className="text-[11px] font-medium text-ink-400">{k}</dt>
              <dd className="mono mt-0.5 truncate text-base font-medium text-ink-100">{v}</dd>
            </div>
          ))}
        </dl>
      )}

      <section aria-label="Tools" className="grid gap-5 md:grid-cols-3">
        {MODULES.map((m) => (
          <Link key={m.to} to={m.to} aria-label={m.title} className="panel group flex flex-col overflow-hidden rounded-[10px] no-underline transition-colors duration-150 hover:border-accent/60">
            <div className="aspect-video overflow-hidden border-b border-ink-700 bg-[#080b12]">
              <img src={`${import.meta.env.BASE_URL}screenshots/${m.shot}`} alt={`${m.title} screenshot`} loading="lazy" className="h-full w-full object-cover opacity-90 transition-[opacity,transform] duration-300 group-hover:scale-[1.02] group-hover:opacity-100 motion-reduce:transition-none"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
            </div>
            <div className="flex flex-1 flex-col p-5">
              <div className="eyebrow !text-ink-400">{m.kicker}</div>
              <h2 className="mt-1 text-base font-semibold text-ink-100">{m.title}</h2>
              <p className="mt-2 flex-1 text-[13px] leading-relaxed text-ink-300">{m.text}</p>
              <span aria-hidden className="mt-4 inline-flex items-center gap-1.5 text-[13px] font-medium text-accent">Open <Arrow /></span>
            </div>
          </Link>
        ))}
      </section>

      <div className="grid gap-5 md:grid-cols-2">
        <Section title="System status">
          {STATIC_DEMO ? (
            <p className="text-sm leading-relaxed text-ink-300">Static demo build: only the synthetic fixture is available, rendered in your browser. Simulation and physics need the local backend.</p>
          ) : (
            <ul className="text-sm" data-testid="system-status">
              <StatusRow label="Backend">{sys.error ? <span className="text-rose-300">offline — run <code className="mono">make dev</code></span> : sys.data ? <span className="text-emerald-300">online (v{String(sys.data.version)})</span> : <span className="text-ink-400">checking…</span>}</StatusRow>
              <StatusRow label="Full FlyWire v783 brain">{fullBrain ? <span className="text-emerald-300">installed ({fullBrain.n_neurons.toLocaleString()} neurons, validation {fullBrain.validation_status})</span> : <span className="text-amber-300">not installed — <code className="mono">uv run flymind data fetch flywire-783</code></span>}</StatusRow>
              <StatusRow label="Neuron skeletons">{caps.skeletons_installed ? <span className="text-emerald-300">installed</span> : <span className="text-amber-300">not installed (optional, 5.4 GB)</span>}</StatusRow>
              <StatusRow label="MuJoCo / FlyGym">{caps.flygym ? <span className="text-emerald-300">available</span> : <span className="text-rose-300">missing</span>}</StatusRow>
              <StatusRow label="Brian2 reference engine">{caps.brian2 ? <span className="text-emerald-300">available</span> : <span className="text-ink-400">missing</span>}</StatusRow>
            </ul>
          )}
        </Section>
        <Section title="How to read results">
          <ul className="space-y-2.5 text-sm">
            {Object.entries(ev.data ?? {}).map(([k, v]) => (
              <li key={k} className="grid grid-cols-[8.5rem_1fr] items-start gap-3">
                <span><EvidenceBadge kind={k as Evidence} /></span>
                <span className="text-[13px] leading-snug text-ink-300">{v}</span>
              </li>
            ))}
          </ul>
        </Section>
      </div>

      <section aria-labelledby="scope-title">
        <h2 id="scope-title" className="panel-title mb-4">Scientific scope</h2>
        <div className="grid gap-x-8 gap-y-6 text-[13px] leading-relaxed text-ink-300 md:grid-cols-3">
          <div className="border-t border-ink-700 pt-3"><h3 className="mb-1.5 text-sm font-semibold text-ink-100">What is real</h3>Neuron identities, positions, cell-type annotations, synapse counts and reconstructed morphology come from the FlyWire FAFB v783 release (Dorkenwald et al. 2024; Schlegel et al. 2024). Neurotransmitters are machine-learning predictions (Eckstein et al. 2024).</div>
          <div className="border-t border-ink-700 pt-3"><h3 className="mb-1.5 text-sm font-semibold text-ink-100">What is assumed</h3>Synaptic strength is proportional to synapse count, transmitter predictions set the sign, neurons are point LIF units with one shared parameter set. These follow Shiu et al. (2024) and are not measurements.</div>
          <div className="border-t border-ink-700 pt-3"><h3 className="mb-1.5 text-sm font-semibold text-ink-100">What is not modelled</h3>The FAFB dataset contains no ventral nerve cord, so leg motor circuits are replaced by FlyGym's walking controller. Gap junctions, neuromodulation, plasticity and internal state are absent.</div>
        </div>
      </section>

      <aside aria-labelledby="not-title" className="rounded-lg border border-ink-700 border-l-[3px] border-l-(color:--warn) bg-ink-900 px-5 py-4">
        <h2 id="not-title" className="text-sm font-semibold text-ink-100">What FlyMind is not</h2>
        <p className="mt-1.5 max-w-3xl text-[13px] leading-relaxed text-ink-300">
          It is not a digital twin or emulation of a living fly. The brain model is a network of point neurons with shared
          parameters, and its output is simulation, not recorded activity. Walking in the Virtual Fly comes from an external
          controller driven by a small set of descending neurons, so behaviour should not be read as a prediction of what a real
          fly would do. The synthetic demonstration fixture is not the connectome of any animal. Use the evidence badges to tell
          reconstructed data, reproduced results and hypotheses apart.
        </p>
      </aside>
    </div>
  );
}

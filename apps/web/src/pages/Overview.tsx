import { Link } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { EvidenceBadge, Section, useAsync, useDatasets } from "../components/ui";
import type { Evidence } from "../lib/types";

const MODULES = [
  {
    to: "/explorer", title: "Brain Explorer 3D", shot: "explorer.png",
    text: "All 139,255 proofread FlyWire v783 neurons in anatomical space. Search by ID or cell type, inspect inputs and outputs, trace pathways, load reconstructed skeletons and overlay simulated activity.",
  },
  {
    to: "/simulator", title: "Brain Simulator", shot: "simulator.png",
    text: "Leaky integrate-and-fire dynamics on the real connectome (Shiu et al. 2024 model), with full-brain, region, circuit and demonstration modes, live stimulation, silencing and reversible lesions.",
  },
  {
    to: "/fly", title: "Virtual Fly", shot: "fly.png",
    text: "The official NeuroMechFly body in MuJoCo (FlyGym 2.x). Sensors feed the neural model through a documented interface; descending-neuron activity drives a CPG walking controller.",
  },
];

export default function Overview() {
  const ds = useDatasets();
  const sys = useAsync(() => (STATIC_DEMO ? Promise.resolve(null) : api.system()), []);
  const ev = useAsync(() => api.evidence(), []);
  const caps = (sys.data?.capabilities ?? {}) as Record<string, boolean>;
  const fullBrain = ds.data?.find((d) => d.dataset_id === "flywire_fafb_783");
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-6">
      <section className="relative overflow-hidden rounded-2xl border border-ink-800 bg-gradient-to-br from-ink-900 via-ink-900 to-[#151033] p-8">
        <div className="max-w-3xl">
          <p className="mb-2 text-xs font-semibold uppercase tracking-[0.2em] text-accent">Virtual Drosophila laboratory</p>
          <h1 className="text-3xl font-semibold leading-tight md:text-4xl">Simulate, embody and explore the fruit-fly connectome.</h1>
          <p className="mt-3 text-ink-300">
            FlyMind connects the FlyWire whole-brain wiring diagram of an adult female <i>Drosophila melanogaster</i> to a
            reproducible spiking-network model, a physics-based body and an interactive 3D anatomy viewer, and keeps the
            difference between reconstructed data, model assumptions and simulation output visible throughout.
          </p>
          <div className="mt-5 flex flex-wrap gap-2">
            <Link to="/explorer" className="btn btn-primary">Open the Brain Explorer</Link>
            <Link to="/experiments" className="btn">Run an experiment</Link>
            <Link to="/docs" className="btn">Read the methods</Link>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-3">
        {MODULES.map((m) => (
          <Link key={m.to} to={m.to} className="panel group overflow-hidden transition hover:border-accent/50">
            <div className="aspect-video overflow-hidden bg-ink-950">
              <img src={`${import.meta.env.BASE_URL}screenshots/${m.shot}`} alt={`${m.title} screenshot`} className="h-full w-full object-cover opacity-90 transition group-hover:opacity-100"
                onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }} />
            </div>
            <div className="p-4">
              <h2 className="font-semibold text-ink-100">{m.title}</h2>
              <p className="mt-1 text-sm text-ink-300">{m.text}</p>
            </div>
          </Link>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Section title="System status">
          {STATIC_DEMO ? (
            <p className="text-sm text-ink-300">Static demo build: only the synthetic fixture is available, rendered in your browser. Simulation and physics need the local backend.</p>
          ) : (
            <ul className="space-y-1 text-sm" data-testid="system-status">
              <li>Backend: {sys.error ? <span className="text-rose-300">offline — run <code className="mono">make dev</code></span> : sys.data ? <span className="text-emerald-300">online (v{String(sys.data.version)})</span> : "checking…"}</li>
              <li>Full FlyWire v783 brain: {fullBrain ? <span className="text-emerald-300">installed ({fullBrain.n_neurons.toLocaleString()} neurons, validation {fullBrain.validation_status})</span> : <span className="text-amber-300">not installed — <code className="mono">uv run flymind data fetch flywire-783</code></span>}</li>
              <li>Neuron skeletons: {caps.skeletons_installed ? <span className="text-emerald-300">installed</span> : <span className="text-amber-300">not installed (optional, 5.4 GB)</span>}</li>
              <li>MuJoCo / FlyGym: {caps.flygym ? <span className="text-emerald-300">available</span> : <span className="text-rose-300">missing</span>}</li>
              <li>Brian2 reference engine: {caps.brian2 ? <span className="text-emerald-300">available</span> : "missing"}</li>
            </ul>
          )}
        </Section>
        <Section title="How to read results">
          <ul className="space-y-1.5 text-sm">
            {Object.entries(ev.data ?? {}).map(([k, v]) => <li key={k} className="flex items-start gap-2"><EvidenceBadge kind={k as Evidence} /><span className="text-ink-300">{v}</span></li>)}
          </ul>
        </Section>
      </div>

      <Section title="Scientific scope">
        <div className="grid gap-4 text-sm text-ink-300 md:grid-cols-3">
          <p><b className="text-ink-100">What is real.</b> Neuron identities, positions, cell-type annotations, synapse counts and reconstructed morphology come from the FlyWire FAFB v783 release (Dorkenwald et al. 2024; Schlegel et al. 2024). Neurotransmitters are machine-learning predictions (Eckstein et al. 2024).</p>
          <p><b className="text-ink-100">What is assumed.</b> Synaptic strength is proportional to synapse count, transmitter predictions set the sign, neurons are point LIF units with one shared parameter set. These follow Shiu et al. (2024) and are not measurements.</p>
          <p><b className="text-ink-100">What is not modelled.</b> The FAFB dataset contains no ventral nerve cord, so leg motor circuits are replaced by FlyGym's walking controller. Gap junctions, neuromodulation, plasticity and internal state are absent.</p>
        </div>
      </Section>
    </div>
  );
}

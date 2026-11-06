import { Link } from "react-router-dom";
import { STATIC_DEMO, api } from "../lib/api";
import { useApp } from "../lib/store";
import { EVIDENCE_KINDS, EvidenceBadge, Figure, KV, Section, fmt, useAsync, useDatasets } from "../components/ui";
import { Icon } from "../components/Icon";
import { WingFigure } from "../components/WingFigure";

const IMG = (name: string) => `${import.meta.env.BASE_URL}screenshots/${name}`;

/** A coloured square plus text: how installation status is written (no pills). */
function Status({ tone, children }: { tone: "ok" | "warn" | "danger" | "muted"; children: React.ReactNode }) {
  const c = { ok: "var(--ok)", warn: "var(--warn)", danger: "var(--danger)", muted: "var(--ink-4)" }[tone];
  return (
    <span className="inline-flex items-baseline gap-2 text-right">
      <span aria-hidden className="relative top-[-1px] inline-block h-[7px] w-[7px] shrink-0 self-center" style={{ background: c }} />
      <span>{children}</span>
    </span>
  );
}

function Shot({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="overflow-hidden border border-rule bg-[#121110]" style={{ aspectRatio: "5 / 3" }}>
      <img src={IMG(src)} alt={alt} loading="lazy" className="h-full w-full object-cover" onError={(e) => { (e.target as HTMLImageElement).style.visibility = "hidden"; }} />
    </div>
  );
}

function InstrumentText({ n, title, to, children }: { n: string; title: string; to: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="idx mb-2">{n}</div>
      <h3 className="t-head"><Link to={to} className="no-underline hover:text-ink">{title}</Link></h3>
      <p className="t-body mt-3 text-ink-2">{children}</p>
      <Link to={to} className="mt-4 inline-flex items-center gap-2 text-sm text-ink" aria-label={`Open ${title.toLowerCase()}`}>
        Open <Icon name="arrow-right" size={14} />
      </Link>
    </div>
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
    <div className="mx-auto max-w-[1280px] px-8 pb-24">
      {/* ------------------------------------------------------------ opening */}
      <section aria-labelledby="hero-title" className="grid grid-cols-12 gap-x-6 gap-y-10 pb-16 pt-14">
        <div className="col-span-12 lg:col-span-6">
          <p className="mb-6 text-sm text-ink-3">A virtual laboratory for the adult fruit-fly brain</p>
          <h1 id="hero-title" className="t-display text-ink" style={{ textWrap: "balance" }}>
            The fruit-fly connectome, simulated and embodied.
          </h1>
          <p className="t-lead mt-6 max-w-[46ch] text-ink-2">
            FlyMind runs a spiking-network model on the FlyWire wiring diagram of an adult female <i>Drosophila melanogaster</i>,
            couples it to a physics-based body, and keeps reconstructed data, model assumptions and simulation output visibly apart.
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-x-6 gap-y-3">
            <Link to="/explorer" className="btn btn-primary h-9 px-4 text-sm no-underline hover:text-[var(--on-accent)]">
              Open the brain explorer <Icon name="arrow-right" size={14} />
            </Link>
            <Link to="/experiments" className="text-sm">Run an experiment</Link>
            <Link to="/docs" className="text-sm">Read the methods</Link>
          </div>
          <KV className="mt-12 max-w-[420px] border-t border-rule-strong" rows={[
            ["Active dataset", active ? (active.synthetic ? "Synthetic fixture" : `${active.name} v${active.version}`) : "–"],
            ["Neurons", fmt.int(active?.n_neurons)],
            ["Connections", fmt.int(active?.n_edges)],
            ["Synapses", fmt.int(active?.n_synapses)],
          ]} />
        </div>
        <div className="col-span-12 lg:col-span-6 lg:-mr-6">
          <Figure n={1} caption="Venation of the Drosophila wing: longitudinal veins L1 to L5, the anterior and posterior cross-veins (acv, pcv) and margin bristles. A schematic drawn for this interface, not data.">
            <WingFigure className="h-auto w-full" />
          </Figure>
        </div>
      </section>

      {/* ------------------------------------------------------------ instruments */}
      <Section n="01" title="Three instruments" className="!pt-6">
        <div className="space-y-16 pt-4">
          <div className="grid grid-cols-12 items-start gap-x-6 gap-y-6">
            <div className="col-span-12 md:col-span-4">
              <InstrumentText n="Anatomy" title="Brain explorer" to="/explorer">
                All 139,255 proofread neurons of FlyWire v783 in anatomical space. Search by root ID or cell type, read a neuron's inputs
                and outputs, trace the shortest pathway between two cells, load reconstructed skeletons, and colour the brain by simulated activity.
              </InstrumentText>
            </div>
            <Figure n={2} className="col-span-12 md:col-span-8" caption="Brain explorer with FlyWire v783 loaded. Neurons are coloured by super class; the descending neuron DNa02 is selected and its reconstructed skeleton drawn.">
              <Shot src="explorer.png" alt="Brain explorer: neuron point cloud with a selected neuron and its skeleton" />
            </Figure>
          </div>
          <div className="grid grid-cols-12 items-start gap-x-6 gap-y-6">
            <Figure n={3} className="order-2 col-span-12 md:order-1 md:col-span-7" caption="Brain simulator, full-brain mode, with the sugar-sensing receptor group driven at 200 Hz. The raster and rates are simulation output of the leaky integrate-and-fire model.">
              <Shot src="simulator.png" alt="Brain simulator: spike raster and population firing rates" />
            </Figure>
            <div className="order-1 col-span-12 md:order-2 md:col-span-4 md:col-start-9">
              <InstrumentText n="Dynamics" title="Brain simulator" to="/simulator">
                Leaky integrate-and-fire dynamics on the real wiring diagram, following Shiu et al. (2024). Run the full brain, one region or a
                circuit you select, and stimulate, silence or partly lesion neurons while it runs.
              </InstrumentText>
            </div>
          </div>
          <div className="grid grid-cols-12 items-start gap-x-6 gap-y-6">
            <div className="col-span-12 md:col-span-4">
              <InstrumentText n="Embodiment" title="Virtual fly" to="/fly">
                The NeuroMechFly body in MuJoCo (FlyGym 2.x). Sensors feed the neural model through a documented interface, and descending-neuron
                activity drives a central-pattern-generator walking controller. A separate FlyMind flight model lets the body take off and land.
              </InstrumentText>
            </div>
            <Figure n={4} className="col-span-12 md:col-span-6 md:col-start-6" caption="Virtual fly in the food arena. The body pose is streamed from MuJoCo; walking comes from FlyGym's controller.">
              <Shot src="fly.png" alt="Virtual fly walking in the food arena" />
            </Figure>
          </div>
        </div>
      </Section>

      {/* ------------------------------------------------------------ reading results, with marginalia */}
      <div className="mt-24 grid grid-cols-12 gap-x-6 gap-y-16">
        <div className="col-span-12 space-y-16 lg:col-span-7">
          <Section n="02" title="How to read a result">
            <ul className="border-t border-rule">
              {EVIDENCE_KINDS.map((k) => (
                <li key={k} className="grid grid-cols-[9.5rem_1fr] items-baseline gap-4 border-b border-rule py-3">
                  <EvidenceBadge kind={k} />
                  <span className="text-sm text-ink-2">{ev.data?.[k] ?? ""}</span>
                </li>
              ))}
            </ul>
          </Section>

          <Section n="03" title="Scientific scope">
            <dl className="border-t border-rule">
              {[
                ["What is real", "Neuron identities, positions, cell-type annotations, synapse counts and reconstructed morphology come from the FlyWire FAFB v783 release (Dorkenwald et al. 2024; Schlegel et al. 2024). Neurotransmitters are machine-learning predictions (Eckstein et al. 2024)."],
                ["What is assumed", "Synaptic strength is proportional to synapse count, the predicted transmitter sets the sign, and every neuron is a point LIF unit with one shared parameter set. These follow Shiu et al. (2024) and are not measurements."],
                ["What is not modelled", "The FAFB dataset has no ventral nerve cord, so leg motor circuits are replaced by FlyGym's walking controller. Gap junctions, neuromodulation, plasticity and internal state are absent."],
              ].map(([h, t]) => (
                <div key={h} className="grid gap-x-6 gap-y-1 border-b border-rule py-4 md:grid-cols-[11rem_1fr]">
                  <dt className="t-head !text-[17px] !leading-6">{h}</dt>
                  <dd className="text-sm leading-6 text-ink-2">{t}</dd>
                </div>
              ))}
            </dl>
          </Section>
        </div>

        <div className="col-span-12 space-y-16 lg:col-span-4 lg:col-start-9">
          <Section n="04" title="This installation">
            {STATIC_DEMO ? (
              <p className="text-sm leading-6 text-ink-2">Static demo build: only the synthetic fixture is available, rendered in your browser. Simulation and physics need the local backend.</p>
            ) : (
              <KV className="kv-sans border-t border-rule" testId="system-status" rows={[
                ["Backend", sys.error ? <Status tone="danger">offline; run <code>make dev</code></Status> : sys.data ? <Status tone="ok">online, v{String(sys.data.version)}</Status> : <Status tone="muted">checking</Status>],
                ["FlyWire v783 brain", fullBrain ? <Status tone="ok">installed, validation {fullBrain.validation_status}</Status> : <Status tone="warn">not installed</Status>],
                ["Neuron skeletons", caps.skeletons_installed ? <Status tone="ok">installed</Status> : <Status tone="warn">not installed (optional, 5.4 GB)</Status>],
                ["MuJoCo and FlyGym", caps.flygym ? <Status tone="ok">available</Status> : <Status tone="danger">missing</Status>],
                ["Brian2 reference engine", caps.brian2 ? <Status tone="ok">available</Status> : <Status tone="muted">missing</Status>],
              ]} />
            )}
            {!STATIC_DEMO && !fullBrain && <p className="mt-3 text-xs text-ink-3">Install the full brain with <code>uv run flymind data fetch flywire-783</code>.</p>}
          </Section>

          <aside aria-labelledby="not-title" className="border-l-2 border-ink pl-5">
            <h2 id="not-title" className="t-head">What FlyMind is not</h2>
            <p className="t-caption mt-3 !text-[15px] !leading-6">
              It is not a digital twin or an emulation of a living fly. The brain model is a network of point neurons with shared parameters,
              and its output is simulation, not recorded activity. Walking in the Virtual fly comes from an external controller driven by a
              small set of descending neurons, so the behaviour is not a prediction of what a real fly would do. The synthetic demonstration
              fixture is not the connectome of any animal. The evidence marks keep reconstructed data, reproduced results and hypotheses apart.
            </p>
          </aside>
        </div>
      </div>
    </div>
  );
}

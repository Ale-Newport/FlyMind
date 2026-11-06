import { useEffect, useMemo, useState } from "react";
import { STATIC_DEMO, api } from "../lib/api";
import { useApp } from "../lib/store";
import type { ExperimentListItem, ExperimentSpec, Job, TemplateInfo } from "../lib/types";
import { Plot } from "../components/Plot";
import { Empty, ErrorBox, EvidenceBadge, Field, Loading, Section, fmt, useAsync, useInterval } from "../components/ui";
import { hashColor } from "../lib/colors";

interface Readout { condition: string; readout: string; n_neurons: number; mean_rate_hz: number; std_hz: number }
interface ExpDetail {
  record: Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
  spec?: ExperimentSpec;
  files: string[];
  readouts?: Readout[];
  timecourse?: { condition: string; readout: string; t_ms: number; rate_hz: number }[];
  regions?: { condition: string; label: string; spikes: number; neurons: number; mean_rate_hz: number }[];
  embodied_runs: string[];
}

export default function Experiments() {
  const { datasetId } = useApp();
  const [openId, setOpenId] = useState<string | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const list = useAsync<ExperimentListItem[]>(() => (STATIC_DEMO ? Promise.resolve([]) : api.experiments()), [job?.status]);
  if (STATIC_DEMO) return <div className="p-6"><Empty title="Experiments run on the local backend">Results are produced by the Python engine; see docs/evidence for the recorded reference runs.</Empty></div>;
  return (
    <div className="grid h-full grid-cols-[24rem_1fr] gap-3 p-3">
      <div className="space-y-3 overflow-y-auto">
        <TemplatePanel datasetId={datasetId} job={job} setJob={setJob} onDone={(id) => { list.reload(); setOpenId(id); }} />
        <Section title="Saved experiments" right={<button className="btn px-1.5 py-0 text-[11px]" onClick={list.reload}>↻</button>}>
          {list.loading ? <Loading /> : (list.data ?? []).length === 0 ? <p className="text-xs text-ink-400">None yet.</p> : (
            <ul className="space-y-1 text-xs" data-testid="experiment-list">
              {(list.data ?? []).map((e) => (
                <li key={e.experiment_id}>
                  <button className={`w-full rounded border px-2 py-1 text-left hover:bg-ink-800 ${openId === e.experiment_id ? "border-accent/60" : "border-ink-700"}`} onClick={() => setOpenId(e.experiment_id)}>
                    <div className="flex items-center gap-2"><span className="flex-1 font-medium">{e.name}</span><EvidenceBadge kind={e.evidence} /></div>
                    <div className="mono text-[10px] text-ink-400">{e.experiment_id} · {e.dataset_id}</div>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Section>
        <ComparePanel experiments={list.data ?? []} />
      </div>
      <div className="min-w-0 overflow-y-auto">
        {openId ? <ExperimentView id={openId} /> : <Empty title="Select or run an experiment">Templates cover activation, stimulation sweeps, silencing, propagation, documented sensory circuits, parameter and lesion comparisons, repeated stimuli and embodied runs.</Empty>}
      </div>
    </div>
  );
}

function TemplatePanel({ datasetId, job, setJob, onDone }: { datasetId: string; job: Job | null; setJob: (j: Job | null) => void; onDone: (id: string) => void }) {
  const templates = useAsync<TemplateInfo[]>(() => api.templates(datasetId), [datasetId]);
  const [key, setKey] = useState("");
  const [spec, setSpec] = useState<ExperimentSpec | null>(null);
  const [err, setErr] = useState<Error | null>(null);
  const avail = (templates.data ?? []).filter((t) => t.available);
  useEffect(() => { if (avail.length && !avail.some((t) => t.key === key)) setKey(avail[0].key); }, [avail, key]);
  useEffect(() => { setSpec(avail.find((t) => t.key === key)?.spec ?? null); }, [key, templates.data]);  // eslint-disable-line react-hooks/exhaustive-deps
  useInterval(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    api.job(job.id).then((j) => { setJob(j); if (j.status === "done" && j.result?.experiment_id) onDone(j.result.experiment_id); }, setErr);
  }, job && ["queued", "running"].includes(job.status) ? 700 : null);
  const run = () => spec && api.runExperiment(spec).then((r) => api.job(r.job_id).then(setJob), setErr);
  const embodied = !!spec?.embodiment;
  return (
    <Section title="Run a template">
      {templates.loading ? <Loading /> : avail.length === 0 ? <p className="text-xs text-ink-400">No templates for this dataset.</p> : (
        <div className="space-y-2 text-sm">
          <select aria-label="Template" className="input" value={key} onChange={(e) => setKey(e.target.value)}>
            {avail.map((t) => <option key={t.key} value={t.key}>{t.title}</option>)}
          </select>
          {spec && (
            <>
              <div className="flex items-center gap-2"><span className="font-medium">{spec.name}</span><EvidenceBadge kind={spec.evidence} /></div>
              <p className="text-xs text-ink-400">{spec.description}</p>
              <div className="text-xs text-ink-300">Conditions: {spec.conditions.map((c) => c.name).join(" · ")}</div>
              <div className="text-xs text-ink-300">Readouts: {spec.readouts.map((r) => r.name).join(", ") || "—"}</div>
              <div className="grid grid-cols-3 gap-2">
                <Field label="Trials"><input type="number" className="input" min={1} max={100} value={spec.n_trials} disabled={embodied} onChange={(e) => setSpec({ ...spec, n_trials: +e.target.value })} /></Field>
                <Field label="Duration ms"><input type="number" className="input" min={10} value={spec.duration_ms} disabled={embodied} onChange={(e) => setSpec({ ...spec, duration_ms: +e.target.value })} /></Field>
                <Field label="Seed"><input type="number" className="input" min={0} value={spec.seed} onChange={(e) => setSpec({ ...spec, seed: +e.target.value })} /></Field>
              </div>
              {embodied && <p className="text-xs text-amber-200">Embodied runs step MuJoCo and the brain together; expect minutes of wall time.</p>}
              <button className="btn btn-primary w-full" onClick={run} disabled={!!job && ["queued", "running"].includes(job.status)}>Run experiment</button>
            </>
          )}
          <ErrorBox error={err} />
          {job && (
            <div className="rounded border border-ink-700 p-2 text-xs" data-testid="job-status">
              <div className="flex justify-between"><span>{job.label}</span><span>{job.status}</span></div>
              <div className="mt-1 h-1.5 rounded bg-ink-800"><div className="h-1.5 rounded bg-accent" style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <div className="mt-1 text-ink-400">{job.message}</div>
              {job.error && <div className="text-rose-300">{job.error}</div>}
              {["queued", "running"].includes(job.status) && <button className="btn mt-1 py-0 text-[11px]" onClick={() => api.cancelJob(job.id).then(setJob)}>Cancel</button>}
            </div>
          )}
        </div>
      )}
    </Section>
  );
}

function ExperimentView({ id }: { id: string }) {
  const d = useAsync<ExpDetail>(() => api.experiment(id) as unknown as Promise<ExpDetail>, [id]);
  if (d.loading) return <Loading />;
  if (d.error || !d.data) return <ErrorBox error={d.error} />;
  const { record, readouts = [], timecourse = [], regions = [], files, embodied_runs } = d.data;
  const conds = Array.from(new Set(readouts.map((r) => r.condition)));
  const names = Array.from(new Set(readouts.map((r) => r.readout)));
  return (
    <div className="space-y-3">
      <Section title="Experiment" right={<EvidenceBadge kind={record.evidence} />}>
        <h1 className="text-lg font-semibold">{record.name ?? id}</h1>
        <p className="text-sm text-ink-300">{d.data.spec?.description}</p>
        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-0.5 text-xs md:grid-cols-4">
          <span className="text-ink-400">ID</span><span className="mono">{record.experiment_id}</span>
          <span className="text-ink-400">Dataset</span><span>{record.dataset?.dataset_id} v{record.dataset?.version}{record.dataset?.synthetic ? " (synthetic)" : ""}</span>
          <span className="text-ink-400">Network</span><span>{record.network?.mode} · {fmt.int(record.network?.n_neurons)} neurons</span>
          <span className="text-ink-400">Wall time</span><span>{fmt.num(record.wall_total_s)} s</span>
          <span className="text-ink-400">Seeds</span><span className="mono">{record.seeds?.base} (+trial)</span>
          <span className="text-ink-400">Software</span><span className="mono">flymind {record.runtime?.flymind_version} · {String(record.runtime?.git_commit ?? "").slice(0, 10)}</span>
        </div>
        <div className="mt-2 flex flex-wrap gap-1">
          {files.map((f) => <a key={f} className="btn py-0.5 text-xs" href={api.experimentFileUrl(id, f)}>{f}</a>)}
        </div>
      </Section>
      {readouts.length > 0 && (
        <Section title="Readouts (mean ± SD across trials)">
          <Plot testId="readout-bars" height={260} data={names.map((n) => ({
            type: "bar", name: n, x: conds, y: conds.map((c) => readouts.find((r) => r.condition === c && r.readout === n)?.mean_rate_hz ?? 0),
            error_y: { type: "data", array: conds.map((c) => readouts.find((r) => r.condition === c && r.readout === n)?.std_hz ?? 0), visible: true },
            marker: { color: hashColor(n) },
          }))} layout={{ barmode: "group", yaxis: { title: { text: "Hz per neuron" } } }} />
          <table className="table mt-2">
            <thead><tr><th>Condition</th><th>Readout</th><th>Neurons</th><th>Mean (Hz)</th><th>SD</th></tr></thead>
            <tbody>{readouts.map((r, i) => <tr key={i}><td>{r.condition}</td><td>{r.readout}</td><td>{r.n_neurons}</td><td className="mono">{r.mean_rate_hz.toFixed(2)}</td><td className="mono">{r.std_hz.toFixed(2)}</td></tr>)}</tbody>
          </table>
        </Section>
      )}
      {record.expected_checks?.length > 0 && (
        <Section title="Comparison with published / reference values">
          <table className="table" data-testid="expected-checks">
            <thead><tr><th>Readout</th><th>Condition</th><th>Reference</th><th>Observed</th><th>Tolerance</th><th>Status</th></tr></thead>
            <tbody>{record.expected_checks.map((c: Record<string, any>, i: number) => (  // eslint-disable-line @typescript-eslint/no-explicit-any
              <tr key={i}><td>{c.readout}</td><td>{c.condition}</td><td className="mono">{c.value_hz}</td><td className="mono">{c.observed_hz == null ? "–" : c.observed_hz.toFixed(2)}</td><td>±{c.tolerance_hz}</td>
                <td className={c.status === "pass" ? "text-emerald-300" : "text-rose-300"}>{c.status}</td></tr>
            ))}</tbody>
          </table>
          <p className="mt-1 text-[11px] text-ink-400">{record.expected_checks[0]?.source}</p>
        </Section>
      )}
      {timecourse.length > 0 && (
        <Section title="Time course (trial-averaged)">
          <Plot testId="timecourse" height={260} data={Array.from(new Set(timecourse.map((r) => `${r.condition} · ${r.readout}`))).map((k) => {
            const rows = timecourse.filter((r) => `${r.condition} · ${r.readout}` === k);
            return { type: "scatter", mode: "lines", name: k, x: rows.map((r) => r.t_ms), y: rows.map((r) => r.rate_hz), line: { width: 1.5, color: hashColor(k) } };
          })} layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "Hz" } } }} />
        </Section>
      )}
      {regions.length > 0 && (
        <Section title="Regional activity (top regions)">
          <Plot height={240} data={conds.map((c) => {
            const rows = regions.filter((r) => r.condition === c).slice(0, 15);
            return { type: "bar", name: c, x: rows.map((r) => r.label), y: rows.map((r) => r.mean_rate_hz), marker: { color: hashColor(c) } };
          })} layout={{ barmode: "group", yaxis: { title: { text: "mean Hz / neuron" } } }} />
        </Section>
      )}
      {embodied_runs.length > 0 && <EmbodiedRuns id={id} runs={embodied_runs} record={record} />}
      {record.assumptions?.length > 0 && (
        <Section title="Model assumptions">
          <ul className="list-disc space-y-0.5 pl-5 text-xs text-ink-300">{record.assumptions.map((a: string) => <li key={a}>{a}</li>)}</ul>
        </Section>
      )}
    </div>
  );
}

function EmbodiedRuns({ id, runs, record }: { id: string; runs: string[]; record: Record<string, any> }) {  // eslint-disable-line @typescript-eslint/no-explicit-any
  const [data, setData] = useState<Record<string, Record<string, number>[]>>({});
  useEffect(() => { runs.forEach((r) => api.embodiedTrajectory(id, r).then((t) => setData((d) => ({ ...d, [r]: t.rows })))); }, [id, runs]);
  const metrics = Object.entries(record.resolved_neurons ?? {}).flatMap(([cond, v]) => ((v as { embodied?: { metrics: Record<string, number> } }).embodied ? [[cond, (v as { embodied: { metrics: Record<string, number> } }).embodied.metrics] as const] : []));
  const keys = ["distance_travelled_mm", "net_displacement_mm", "mean_speed_mm_s", "heading_change_deg", "collision_onsets", "min_dist_attractive_source_mm"];
  return (
    <Section title="Embodied runs">
      <Plot testId="embodied-paths" height={300} data={Object.entries(data).map(([r, rows]) => ({ type: "scatter", mode: "lines", name: r.replace("fly_", ""), x: rows.map((x) => x.x_mm), y: rows.map((x) => x.y_mm), line: { color: hashColor(r) } }))}
        layout={{ xaxis: { title: { text: "x (mm)" } }, yaxis: { title: { text: "y (mm)" }, scaleanchor: "x" } }} />
      <table className="table mt-2">
        <thead><tr><th>Condition</th>{keys.map((k) => <th key={k}>{k.replace(/_/g, " ")}</th>)}</tr></thead>
        <tbody>{metrics.map(([c, m]) => <tr key={c}><td>{c}</td>{keys.map((k) => <td key={k} className="mono">{m[k] == null ? "–" : Number(m[k]).toFixed(1)}</td>)}</tr>)}</tbody>
      </table>
      <p className="mt-1 text-[11px] text-ink-400">Observations: trajectories and metrics. Interpretation (e.g. “approach”) requires comparison with the baseline and across seeds.</p>
    </Section>
  );
}

function ComparePanel({ experiments }: { experiments: ExperimentListItem[] }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [ca, setCa] = useState("");
  const [cb, setCb] = useState("");
  const [res, setRes] = useState<Record<string, any> | null>(null);  // eslint-disable-line @typescript-eslint/no-explicit-any
  const [err, setErr] = useState<Error | null>(null);
  const expA = useMemo(() => experiments.find((e) => e.experiment_id === a), [a, experiments]);
  const expB = useMemo(() => experiments.find((e) => e.experiment_id === b), [b, experiments]);
  const exps = experiments.filter((e) => e.conditions.length);
  return (
    <Section title="Compare results">
      <div className="space-y-1.5 text-xs">
        <select aria-label="Experiment A" className="input" value={a} onChange={(e) => setA(e.target.value)}><option value="">A: experiment…</option>{exps.map((e) => <option key={e.experiment_id} value={e.experiment_id}>{e.name} ({e.experiment_id.slice(0, 15)})</option>)}</select>
        {expA && <select aria-label="Condition A" className="input" value={ca} onChange={(e) => setCa(e.target.value)}><option value="">first condition</option>{expA.conditions.map((c) => <option key={c}>{c}</option>)}</select>}
        <select aria-label="Experiment B" className="input" value={b} onChange={(e) => setB(e.target.value)}><option value="">B: experiment…</option>{exps.map((e) => <option key={e.experiment_id} value={e.experiment_id}>{e.name} ({e.experiment_id.slice(0, 15)})</option>)}</select>
        {expB && <select aria-label="Condition B" className="input" value={cb} onChange={(e) => setCb(e.target.value)}><option value="">last condition</option>{expB.conditions.map((c) => <option key={c}>{c}</option>)}</select>}
        <button className="btn btn-primary w-full" disabled={!a || !b} onClick={() => api.compare(a, b, ca || undefined, cb || undefined).then(setRes, setErr)}>Compare</button>
        <ErrorBox error={err} />
        {res && (
          <div data-testid="compare-result" className="space-y-1">
            {(res.warnings ?? []).map((w: string) => <p key={w} className="text-amber-200">{w}</p>)}
            <div className="text-ink-400">A: {res.a.condition} · B: {res.b.condition}</div>
            <table className="table">
              <thead><tr><th>Readout</th><th>A</th><th>B</th><th>Δ</th></tr></thead>
              <tbody>{(res.readouts ?? []).map((r: Record<string, number | null | string>) => <tr key={String(r.readout)}><td>{r.readout}</td><td className="mono">{fmt.num(r.a_mean_hz as number)}</td><td className="mono">{fmt.num(r.b_mean_hz as number)}</td><td className="mono">{fmt.num(r.delta_hz as number)}</td></tr>)}</tbody>
            </table>
            {res.largest_changes && <>
              <div className="pt-1 text-ink-400">Largest per-neuron changes (Hz)</div>
              <table className="table"><tbody>{res.largest_changes.slice(0, 10).map((r: Record<string, number | string>) => <tr key={r.root_id}><td>{r.cell_type ?? "—"}</td><td className="mono text-[10px]">{r.root_id}</td><td className="mono">{Number(r.delta_hz).toFixed(1)}</td></tr>)}</tbody></table>
            </>}
          </div>
        )}
      </div>
    </Section>
  );
}

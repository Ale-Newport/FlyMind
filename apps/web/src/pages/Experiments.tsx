import { useEffect, useMemo, useState } from "react";
import { STATIC_DEMO, api } from "../lib/api";
import { useApp } from "../lib/store";
import type { ExperimentListItem, ExperimentSpec, Job, TemplateInfo } from "../lib/types";
import { Plot } from "../components/Plot";
import { Block, Empty, ErrorBox, EvidenceBadge, Field, Figure, Group, KV, Loading, Section, fmt, useAsync, useInterval } from "../components/ui";
import { Icon } from "../components/Icon";
import { useChartColors } from "../lib/colors";

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
  if (STATIC_DEMO) return <div className="mx-auto max-w-3xl px-8 py-12"><Empty title="Experiments run on the local backend.">Results are produced by the Python engine. The recorded reference runs are in docs/evidence.</Empty></div>;
  return (
    <div className="tool min-w-[960px]">
      <aside aria-label="Experiment setup" className="rail">
        <Group title="Run a template">
          <TemplatePanel datasetId={datasetId} job={job} setJob={setJob} onDone={(id) => { list.reload(); setOpenId(id); }} />
        </Group>
        <Group title="Saved experiments" meta={list.data ? String(list.data.length) : undefined}>
          {list.loading && !list.data ? <Loading /> : (list.data ?? []).length === 0 ? <p className="text-xs text-ink-3">Nothing saved yet. Run a template to create the first one.</p> : (
            <ul className="-mx-4 -mt-1 text-xs" data-testid="experiment-list">
              {(list.data ?? []).map((e) => {
                const on = openId === e.experiment_id;
                return (
                  <li key={e.experiment_id}>
                    <button aria-current={on ? "true" : undefined} className={`relative block w-full border-t border-rule px-4 py-2 text-left transition-colors duration-150 hover:bg-paper-3 ${on ? "bg-paper-3" : ""}`} onClick={() => setOpenId(e.experiment_id)}>
                      {on && <span aria-hidden className="absolute inset-y-0 left-0 w-0.5 bg-accent" />}
                      <div className="text-[13px] text-ink">{e.name}</div>
                      <div className="mt-1 flex items-center gap-3"><EvidenceBadge kind={e.evidence} /></div>
                      <div className="mono mt-1 truncate text-[11px] text-ink-3">{e.experiment_id} · {e.dataset_id}</div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <button className="btn btn-sm btn-quiet mt-2" onClick={list.reload} aria-label="Refresh saved experiments"><Icon name="refresh" size={12} />Refresh</button>
        </Group>
        <Group title="Compare results" defaultOpen={false}><ComparePanel experiments={list.data ?? []} /></Group>
      </aside>
      {openId ? <ExperimentView id={openId} /> : (
        <div className="min-w-0 flex-1 overflow-y-auto px-8 py-8">
          <Empty title="Select or run an experiment." className="max-w-[60ch]">Templates cover activation, stimulation sweeps, silencing, propagation, documented sensory circuits, parameter and lesion comparisons, repeated stimuli and embodied runs.</Empty>
        </div>
      )}
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
  const busy = !!job && ["queued", "running"].includes(job.status);
  return (
    <>
      {templates.loading ? <Loading /> : avail.length === 0 ? <p className="text-xs text-ink-3">No templates for this dataset.</p> : (
        <div className="space-y-4">
          <select aria-label="Template" className="input" value={key} onChange={(e) => setKey(e.target.value)}>
            {avail.map((t) => <option key={t.key} value={t.key}>{t.title}</option>)}
          </select>
          {spec && (
            <>
              <div>
                <div className="flex items-baseline justify-between gap-3"><span className="text-[13px] font-medium">{spec.name}</span></div>
                <div className="mt-1"><EvidenceBadge kind={spec.evidence} /></div>
                <p className="mt-2 text-xs leading-5 text-ink-3">{spec.description}</p>
              </div>
              <KV flush className="kv-sans" rows={[
                ["Conditions", spec.conditions.map((c) => c.name).join(", ")],
                ["Readouts", spec.readouts.map((r) => r.name).join(", ") || "–"],
              ]} />
              <div className="grid grid-cols-3 gap-3">
                <Field label="Trials"><input type="number" className="input" min={1} max={100} value={spec.n_trials} disabled={embodied} onChange={(e) => setSpec({ ...spec, n_trials: +e.target.value })} /></Field>
                <Field label="Duration" unit="ms"><input type="number" className="input" min={10} value={spec.duration_ms} disabled={embodied} onChange={(e) => setSpec({ ...spec, duration_ms: +e.target.value })} /></Field>
                <Field label="Seed"><input type="number" className="input" min={0} value={spec.seed} onChange={(e) => setSpec({ ...spec, seed: +e.target.value })} /></Field>
              </div>
              {embodied && <p className="text-xs" style={{ color: "var(--warn)" }}>Embodied runs step MuJoCo and the brain together. Expect minutes of wall time.</p>}
              <button className="btn btn-primary btn-block" onClick={run} disabled={busy}>Run experiment</button>
            </>
          )}
          <ErrorBox error={err} />
          {job && (
            <div className="border-t border-rule pt-3 text-xs" data-testid="job-status">
              <div className="flex justify-between gap-2"><span>{job.label}</span><span className="mono">{job.status}</span></div>
              <div className="mt-2 h-[3px] bg-rule" role="progressbar" aria-label="Experiment progress" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(job.progress * 100)}><div className="h-[3px] bg-accent transition-[width] duration-150" style={{ width: `${Math.round(job.progress * 100)}%` }} /></div>
              <div className="mt-2 text-ink-3">{job.message}</div>
              {job.error && <div style={{ color: "var(--danger)" }}>{job.error}</div>}
              {busy && <button className="btn btn-link mt-1 text-xs" onClick={() => api.cancelJob(job.id).then(setJob)}>Cancel</button>}
            </div>
          )}
        </div>
      )}
    </>
  );
}

function ExperimentView({ id }: { id: string }) {
  const d = useAsync<ExpDetail>(() => api.experiment(id) as unknown as Promise<ExpDetail>, [id]);
  const { cat, accent, textMuted } = useChartColors();
  if (d.loading) return <div className="min-w-0 flex-1 px-8 py-8"><Loading /></div>;
  if (d.error || !d.data) return <div className="min-w-0 flex-1 px-8 py-8"><ErrorBox error={d.error} /></div>;
  const { record, readouts = [], timecourse = [], regions = [], files, embodied_runs } = d.data;
  const conds = Array.from(new Set(readouts.map((r) => r.condition)));
  const names = Array.from(new Set(readouts.map((r) => r.readout)));
  const single = names.length === 1;
  let fig = 0;
  return (
    <>
      <article className="min-w-0 flex-1 overflow-y-auto px-8 pb-16 pt-8">
        <div className="max-w-[980px]">
          <header className="mb-10">
            <EvidenceBadge kind={record.evidence} />
            <h1 className="t-title mt-4">{record.name ?? id}</h1>
            {d.data.spec?.description && <p className="t-lead mt-3 max-w-[60ch] text-ink-2">{d.data.spec.description}</p>}
          </header>
          <div className="space-y-14">
            {readouts.length > 0 && (
              <Section title="Readouts">
                <Figure n={++fig} caption="Mean firing rate per neuron, with the standard deviation across trials as error bars.">
                  <Plot testId="readout-bars" height={260} data={names.map((n, i) => ({
                    type: "bar", name: n, x: conds, y: conds.map((c) => readouts.find((r) => r.condition === c && r.readout === n)?.mean_rate_hz ?? 0),
                    error_y: { type: "data", array: conds.map((c) => readouts.find((r) => r.condition === c && r.readout === n)?.std_hz ?? 0), visible: true, color: textMuted, thickness: 1, width: 3 },
                    marker: { color: single ? accent : cat(n) }, ...(i < 0 ? {} : {}),
                  }))} layout={{ barmode: "group", bargap: 0.7, yaxis: { title: { text: "Hz per neuron" } }, showlegend: !single }} />
                </Figure>
                <table className="tbl tbl-fluid mt-6">
                  <thead><tr><th>Condition</th><th>Readout</th><th className="num">Neurons</th><th className="num">Mean (Hz)</th><th className="num">SD (Hz)</th></tr></thead>
                  <tbody>{readouts.map((r, i) => <tr key={i}><td>{r.condition}</td><td>{r.readout}</td><td className="num">{r.n_neurons}</td><td className="num">{r.mean_rate_hz.toFixed(2)}</td><td className="num">{r.std_hz.toFixed(2)}</td></tr>)}</tbody>
                </table>
              </Section>
            )}
            {record.expected_checks?.length > 0 && (
              <Section title="Comparison with published and reference values">
                <table className="tbl tbl-fluid" data-testid="expected-checks">
                  <thead><tr><th>Readout</th><th>Condition</th><th className="num">Reference (Hz)</th><th className="num">Observed (Hz)</th><th className="num">Tolerance (Hz)</th><th>Status</th></tr></thead>
                  <tbody>{record.expected_checks.map((c: Record<string, any>, i: number) => (  // eslint-disable-line @typescript-eslint/no-explicit-any
                    <tr key={i}><td>{c.readout}</td><td>{c.condition}</td><td className="num">{c.value_hz}</td><td className="num">{c.observed_hz == null ? "–" : c.observed_hz.toFixed(2)}</td><td className="num">±{c.tolerance_hz}</td>
                      <td><span className="inline-flex items-center gap-2"><span aria-hidden className="inline-block h-[7px] w-[7px]" style={{ background: c.status === "pass" ? "var(--ok)" : "var(--danger)" }} />{c.status}</span></td></tr>
                  ))}</tbody>
                </table>
                <p className="mt-3 text-xs text-ink-3">{record.expected_checks[0]?.source}</p>
              </Section>
            )}
            {timecourse.length > 0 && (
              <Section title="Time course">
                <Figure n={++fig} caption="Firing rate over time, averaged across trials.">
                  <Plot testId="timecourse" height={260} data={Array.from(new Set(timecourse.map((r) => `${r.condition} · ${r.readout}`))).map((k) => {
                    const rows = timecourse.filter((r) => `${r.condition} · ${r.readout}` === k);
                    return { type: "scatter", mode: "lines", name: k, x: rows.map((r) => r.t_ms), y: rows.map((r) => r.rate_hz), line: { width: 1.5, color: cat(k) } };
                  })} layout={{ xaxis: { title: { text: "time (ms)" } }, yaxis: { title: { text: "Hz" } } }} />
                </Figure>
              </Section>
            )}
            {regions.length > 0 && (
              <Section title="Regional activity">
                <Figure n={++fig} caption="Mean rate per neuron in the 15 most active regions.">
                  <Plot height={240} data={conds.map((c) => {
                    const rows = regions.filter((r) => r.condition === c).slice(0, 15);
                    return { type: "bar", name: c, x: rows.map((r) => r.label), y: rows.map((r) => r.mean_rate_hz), marker: { color: conds.length === 1 ? accent : cat(c) } };
                  })} layout={{ barmode: "group", bargap: 0.35, yaxis: { title: { text: "mean Hz per neuron" } }, showlegend: conds.length > 1 }} />
                </Figure>
              </Section>
            )}
            {embodied_runs.length > 0 && <EmbodiedRuns id={id} runs={embodied_runs} record={record} fig={++fig} />}
            {record.assumptions?.length > 0 && (
              <Section title="Model assumptions">
                <ul className="max-w-[72ch] border-t border-rule">{record.assumptions.map((a: string) => <li key={a} className="border-b border-rule py-2 text-sm leading-6 text-ink-2">{a}</li>)}</ul>
              </Section>
            )}
          </div>
        </div>
      </article>
      <aside aria-label="Experiment record" className="inspector">
        <Block title="Record">
          <KV rows={[
            ["ID", <span key="i" className="break-all">{record.experiment_id}</span>],
            ["Dataset", `${record.dataset?.dataset_id} v${record.dataset?.version}${record.dataset?.synthetic ? " (synthetic)" : ""}`],
            ["Network", `${record.network?.mode}, ${fmt.int(record.network?.n_neurons)} neurons`],
            ["Wall time", fmt.num(record.wall_total_s), "s"],
            ["Seeds", `${record.seeds?.base} (+ trial)`],
            ["Software", `flymind ${record.runtime?.flymind_version}${record.runtime?.git_commit ? `, ${String(record.runtime.git_commit).slice(0, 10)}` : ""}`],
          ]} />
        </Block>
        <Block title="Files">
          <ul className="-mt-1">{files.map((f) => (
            <li key={f} className="border-t border-rule first:border-t-0">
              <a className="flex items-center justify-between gap-2 py-1.5 text-xs no-underline" href={api.experimentFileUrl(id, f)}><span className="mono truncate">{f}</span><Icon name="download" size={12} className="shrink-0 text-ink-3" /></a>
            </li>
          ))}</ul>
        </Block>
      </aside>
    </>
  );
}

function EmbodiedRuns({ id, runs, record, fig }: { id: string; runs: string[]; record: Record<string, any>; fig: number }) {  // eslint-disable-line @typescript-eslint/no-explicit-any
  const { cat } = useChartColors();
  const [data, setData] = useState<Record<string, Record<string, number>[]>>({});
  useEffect(() => { runs.forEach((r) => api.embodiedTrajectory(id, r).then((t) => setData((d) => ({ ...d, [r]: t.rows })))); }, [id, runs]);
  const metrics = Object.entries(record.resolved_neurons ?? {}).flatMap(([cond, v]) => ((v as { embodied?: { metrics: Record<string, number> } }).embodied ? [[cond, (v as { embodied: { metrics: Record<string, number> } }).embodied.metrics] as const] : []));
  const keys = ["distance_travelled_mm", "net_displacement_mm", "mean_speed_mm_s", "heading_change_deg", "collision_onsets", "min_dist_attractive_source_mm"];
  return (
    <Section title="Embodied runs">
      <Figure n={fig} caption="Paths of the fly in each condition, top view.">
        <Plot testId="embodied-paths" height={300} data={Object.entries(data).map(([r, rows]) => ({ type: "scatter", mode: "lines", name: r.replace("fly_", ""), x: rows.map((x) => x.x_mm), y: rows.map((x) => x.y_mm), line: { color: cat(r), width: 1.5 } }))}
          layout={{ xaxis: { title: { text: "x (mm)" } }, yaxis: { title: { text: "y (mm)" }, scaleanchor: "x" } }} />
      </Figure>
      <div className="mt-6 overflow-x-auto">
        <table className="tbl tbl-fluid">
          <thead><tr><th>Condition</th>{keys.map((k) => <th key={k} className="num">{k.replace(/_/g, " ")}</th>)}</tr></thead>
          <tbody>{metrics.map(([c, m]) => <tr key={c}><td>{c}</td>{keys.map((k) => <td key={k} className="num">{m[k] == null ? "–" : Number(m[k]).toFixed(1)}</td>)}</tr>)}</tbody>
        </table>
      </div>
      <p className="mt-3 max-w-[72ch] text-xs text-ink-3">These are observations: trajectories and metrics. An interpretation such as “approach” needs a comparison with the baseline and across seeds.</p>
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
    <div className="space-y-2 text-xs">
      <select aria-label="Experiment A" className="input" value={a} onChange={(e) => setA(e.target.value)}><option value="">A: choose an experiment</option>{exps.map((e) => <option key={e.experiment_id} value={e.experiment_id}>{e.name} ({e.experiment_id.slice(0, 15)})</option>)}</select>
      {expA && <select aria-label="Condition A" className="input" value={ca} onChange={(e) => setCa(e.target.value)}><option value="">first condition</option>{expA.conditions.map((c) => <option key={c}>{c}</option>)}</select>}
      <select aria-label="Experiment B" className="input" value={b} onChange={(e) => setB(e.target.value)}><option value="">B: choose an experiment</option>{exps.map((e) => <option key={e.experiment_id} value={e.experiment_id}>{e.name} ({e.experiment_id.slice(0, 15)})</option>)}</select>
      {expB && <select aria-label="Condition B" className="input" value={cb} onChange={(e) => setCb(e.target.value)}><option value="">last condition</option>{expB.conditions.map((c) => <option key={c}>{c}</option>)}</select>}
      <button className="btn btn-block" disabled={!a || !b} onClick={() => api.compare(a, b, ca || undefined, cb || undefined).then(setRes, setErr)}>Compare</button>
      <ErrorBox error={err} />
      {res && (
        <div data-testid="compare-result" className="space-y-3 pt-2">
          {(res.warnings ?? []).map((w: string) => <p key={w} className="note note-warn">{w}</p>)}
          <div className="text-ink-3">A: {res.a.condition}. B: {res.b.condition}.</div>
          <table className="tbl">
            <thead><tr><th>Readout</th><th className="num">A</th><th className="num">B</th><th className="num">Δ</th></tr></thead>
            <tbody>{(res.readouts ?? []).map((r: Record<string, number | null | string>) => <tr key={String(r.readout)}><td>{r.readout}</td><td className="num">{fmt.num(r.a_mean_hz as number)}</td><td className="num">{fmt.num(r.b_mean_hz as number)}</td><td className="num">{fmt.num(r.delta_hz as number)}</td></tr>)}</tbody>
          </table>
          {res.largest_changes && <>
            <div className="pt-1 text-ink-3">Largest per-neuron changes (Hz)</div>
            <table className="tbl"><tbody>{res.largest_changes.slice(0, 10).map((r: Record<string, number | string>) => <tr key={r.root_id}><td>{r.cell_type ?? "–"}<div className="mono text-[11px] text-ink-3">{r.root_id}</div></td><td className="num">{Number(r.delta_hz).toFixed(1)}</td></tr>)}</tbody></table>
          </>}
        </div>
      )}
    </div>
  );
}

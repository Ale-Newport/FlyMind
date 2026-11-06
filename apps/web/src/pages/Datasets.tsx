import { useState } from "react";
import { api } from "../lib/api";
import type { DatasetSummary } from "../lib/types";
import { Empty, ErrorBox, Loading, Section, Stat, fmt, useAsync, useDatasets } from "../components/ui";

interface Check { name: string; status: string; message: string }

export default function Datasets() {
  const ds = useDatasets();
  const sources = useAsync(() => api.sources(), []);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="mx-auto max-w-6xl space-y-4 p-4">
      <h1 className="text-xl font-semibold">Datasets</h1>
      <ErrorBox error={ds.error} />
      {ds.loading ? <Loading /> : (ds.data ?? []).length === 0 ? (
        <Empty title="No datasets installed">Run <code className="mono">make setup</code> (synthetic demo) or <code className="mono">uv run flymind data fetch flywire-783</code>.</Empty>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {(ds.data ?? []).map((d) => <DatasetCard key={d.dataset_id} d={d} open={open === d.dataset_id} onToggle={() => setOpen(open === d.dataset_id ? null : d.dataset_id)} />)}
        </div>
      )}
      <Section title="Installing real data">
        {!sources.data ? <Loading /> : <Sources data={sources.data as Record<string, any>} />}  {/* eslint-disable-line @typescript-eslint/no-explicit-any */}
      </Section>
    </div>
  );
}

function DatasetCard({ d, open, onToggle }: { d: DatasetSummary; open: boolean; onToggle: () => void }) {
  return (
    <Section title={d.synthetic ? "Synthetic fixture" : `${d.name} v${d.version}`} right={
      <span className={`chip ${d.validation_status === "passed" ? "border-emerald-500/50 text-emerald-300" : d.validation_status === "failed" ? "border-rose-500/50 text-rose-300" : "border-amber-500/50 text-amber-300"}`} data-testid={`validation-${d.dataset_id}`}>validation: {d.validation_status}</span>
    }>
      <div className="mono mb-1 text-xs text-ink-400">{d.dataset_id}</div>
      <p className="mb-2 text-xs text-ink-300">{d.specimen}</p>
      <div className="grid grid-cols-3 gap-2">
        <Stat label="Neurons" value={fmt.int(d.n_neurons)} />
        <Stat label="Connections" value={fmt.int(d.n_edges)} />
        <Stat label="Synapses" value={fmt.int(d.n_synapses)} />
      </div>
      <p className="mt-2 text-[11px] text-ink-400">Licence: {d.license}</p>
      <p className="text-[11px] text-ink-400">Imported {d.imported_at} by {d.adapter}{d.has_skeletons ? " · skeletons installed" : ""}</p>
      <button className="btn mt-2 py-0.5 text-xs" onClick={onToggle} aria-expanded={open}>{open ? "Hide" : "Show"} provenance & validation</button>
      {open && <DatasetDetail id={d.dataset_id} />}
    </Section>
  );
}

function DatasetDetail({ id }: { id: string }) {
  const m = useAsync(() => api.dataset(id), [id]);
  const v = useAsync(() => api.validation(id), [id]);
  if (m.loading || v.loading) return <Loading />;
  const man = (m.data ?? {}) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
  const checks = ((v.data ?? {}) as { checks?: Check[] }).checks ?? [];
  return (
    <div className="mt-3 space-y-3 text-xs">
      <div>
        <div className="panel-title mb-1">Validation checks</div>
        <table className="table" data-testid="validation-table">
          <tbody>{checks.map((c) => (
            <tr key={c.name}><td className={c.status === "pass" ? "text-emerald-300" : c.status === "fail" ? "text-rose-300" : c.status === "warn" ? "text-amber-300" : "text-ink-400"}>{c.status.toUpperCase()}</td><td>{c.name}</td><td className="text-ink-300">{c.message}</td></tr>
          ))}</tbody>
        </table>
      </div>
      <div>
        <div className="panel-title mb-1">Source files (SHA-256)</div>
        <ul className="space-y-0.5">{(man.files ?? []).map((f: Record<string, string>) => <li key={f.name}><span className="text-ink-100">{f.name}</span> <span className="text-ink-400">[{f.role}]</span><div className="mono break-all text-[10px] text-ink-400">{f.sha256}</div></li>)}</ul>
      </div>
      <div>
        <div className="panel-title mb-1">Transformations</div>
        <ul className="list-disc pl-4 text-ink-300">{(man.transformations ?? []).map((t: string) => <li key={t}>{t}</li>)}</ul>
      </div>
      {(man.notes ?? []).length > 0 && <div><div className="panel-title mb-1">Notes</div><ul className="list-disc pl-4 text-amber-200">{man.notes.map((t: string) => <li key={t}>{t}</li>)}</ul></div>}
      <div>
        <div className="panel-title mb-1">Required citations</div>
        <ul className="list-disc pl-4 text-ink-300">{(man.citations ?? []).map((c: { text: string }) => <li key={c.text}>{c.text}</li>)}</ul>
      </div>
      <div className="text-ink-400">Sign policy: {man.sign_policy_source}</div>
    </div>
  );
}

function Sources({ data }: { data: Record<string, any> }) {  // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <div className="space-y-3 text-sm">
      <div className="grid gap-2 md:grid-cols-3">
        {data.bundles.map((b: Record<string, any>) => (  // eslint-disable-line @typescript-eslint/no-explicit-any
          <div key={b.key} className="rounded-lg border border-ink-700 p-3 text-xs">
            <div className="font-medium text-ink-100">{b.title}</div>
            <p className="my-1 text-ink-400">{b.description}</p>
            <code className="mono block rounded bg-ink-950 px-2 py-1 text-accent">{b.command}</code>
            <div className="mt-1 text-ink-400">{b.files.length} file(s), {fmt.int(Math.round(b.files.reduce((s: number, f: { size_bytes: number | null }) => s + (f.size_bytes ?? 0), 0) / 1e6))} MB, checksummed</div>
          </div>
        ))}
      </div>
      <div className="rounded-lg border border-ink-700 p-3 text-xs">
        <div className="font-medium text-ink-100">FlyWire Codex downloads (sign-in required)</div>
        <p className="text-ink-300">{data.codex.note}</p>
        <a className="text-accent underline" href={data.codex.url} target="_blank" rel="noreferrer">{data.codex.url}</a>
      </div>
      <div>
        <div className="panel-title mb-1">Dataset adapters</div>
        <ul className="space-y-0.5 text-xs">{data.adapters.map((a: Record<string, string>) => <li key={a.name}><span className={`chip mr-2 ${a.status === "supported" ? "border-emerald-500/50 text-emerald-300" : "border-amber-500/50 text-amber-300"}`}>{a.status}</span>{a.title} — <span className="text-ink-400">{a.description}</span></li>)}</ul>
      </div>
      <p className="text-xs text-ink-400">{data.license_note}</p>
    </div>
  );
}

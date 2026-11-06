import { useState } from "react";
import { api } from "../lib/api";
import type { DatasetSummary } from "../lib/types";
import { Empty, ErrorBox, KV, Loading, Section, fmt, useAsync, useDatasets } from "../components/ui";

interface Check { name: string; status: string; message: string }

const TONE: Record<string, string> = { pass: "var(--ok)", passed: "var(--ok)", fail: "var(--danger)", failed: "var(--danger)", warn: "var(--warn)" };
const toneOf = (s: string) => TONE[s] ?? "var(--ink-3)";

export default function Datasets() {
  const ds = useDatasets();
  const sources = useAsync(() => api.sources(), []);
  const [open, setOpen] = useState<string | null>(null);
  return (
    <div className="mx-auto max-w-[1120px] px-8 pb-24 pt-14">
      <header className="mb-12 max-w-[60ch]">
        <p className="mb-4 text-sm text-ink-3">Provenance</p>
        <h1 className="t-title">Datasets</h1>
        <p className="t-lead mt-4 text-ink-2">
          The connectomes installed on this machine, with their provenance, licence and validation results. Every result in FlyMind traces back to one of them.
        </p>
      </header>
      <ErrorBox error={ds.error} />
      {ds.loading ? <Loading /> : (ds.data ?? []).length === 0 ? (
        <Empty title="No datasets installed.">Run <code>make setup</code> for the synthetic demo, or <code>uv run flymind data fetch flywire-783</code> for the full brain.</Empty>
      ) : (
        <div className="border-b border-rule">
          {(ds.data ?? []).map((d, i) => <DatasetEntry key={d.dataset_id} n={String(i + 1).padStart(2, "0")} d={d} open={open === d.dataset_id} onToggle={() => setOpen(open === d.dataset_id ? null : d.dataset_id)} />)}
        </div>
      )}
      <Section n={String((ds.data?.length ?? 0) + 1).padStart(2, "0")} title="Installing real data" className="mt-20">
        {!sources.data ? <Loading /> : <Sources data={sources.data as Record<string, any>} />}  {/* eslint-disable-line @typescript-eslint/no-explicit-any */}
      </Section>
    </div>
  );
}

function DatasetEntry({ d, open, onToggle, n }: { d: DatasetSummary; open: boolean; onToggle: () => void; n: string }) {
  return (
    <article className="border-t border-rule py-8">
      <div className="grid grid-cols-12 gap-x-6 gap-y-6">
        <div className="col-span-12 md:col-span-6">
          <div className="idx mb-2">{n}</div>
          <h2 className="t-head">{d.synthetic ? "Synthetic fixture" : `${d.name} v${d.version}`}</h2>
          <div className="mono mt-1 text-xs text-ink-3">{d.dataset_id}</div>
          <p className="t-body mt-4 max-w-[48ch] text-ink-2">{d.specimen}</p>
          <p className="mt-4 inline-flex items-center gap-2 text-sm" data-testid={`validation-${d.dataset_id}`}>
            <span aria-hidden className="inline-block h-[7px] w-[7px]" style={{ background: toneOf(d.validation_status) }} />
            validation: {d.validation_status}
          </p>
        </div>
        <div className="col-span-12 md:col-span-5 md:col-start-8">
          <KV rows={[
            ["Neurons", fmt.int(d.n_neurons)],
            ["Connections", fmt.int(d.n_edges)],
            ["Synapses", fmt.int(d.n_synapses)],
            ["Imported", `${d.imported_at}`],
            ["Adapter", d.adapter],
            d.has_skeletons && ["Skeletons", "installed"],
          ]} />
          <p className="mt-3 text-xs leading-5 text-ink-3">Licence: {d.license}</p>
          <button className="btn btn-sm mt-5" onClick={onToggle} aria-expanded={open}>{open ? "Hide" : "Show"} provenance and validation</button>
        </div>
      </div>
      {open && <DatasetDetail id={d.dataset_id} />}
    </article>
  );
}

function DatasetDetail({ id }: { id: string }) {
  const m = useAsync(() => api.dataset(id), [id]);
  const v = useAsync(() => api.validation(id), [id]);
  if (m.loading || v.loading) return <div className="pt-8"><Loading /></div>;
  const man = (m.data ?? {}) as Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
  const checks = ((v.data ?? {}) as { checks?: Check[] }).checks ?? [];
  const H = ({ children }: { children: React.ReactNode }) => <h3 className="mb-3 text-sm font-medium">{children}</h3>;
  return (
    <div className="mt-10 grid grid-cols-12 gap-x-6 gap-y-10 text-sm">
      <div className="col-span-12">
        <H>Validation checks</H>
        <table className="tbl tbl-fluid" data-testid="validation-table">
          <tbody>{checks.map((c) => (
            <tr key={c.name}>
              <td className="w-16 whitespace-nowrap font-mono" style={{ color: toneOf(c.status) }}>{c.status}</td>
              <td className="whitespace-nowrap">{c.name}</td>
              <td className="text-ink-3">{c.message}</td>
            </tr>
          ))}</tbody>
        </table>
      </div>
      <div className="col-span-12 md:col-span-7">
        <H>Source files, SHA-256</H>
        <ul className="border-t border-rule">{(man.files ?? []).map((f: Record<string, string>) => (
          <li key={f.name} className="border-b border-rule py-2">
            <span>{f.name}</span> <span className="text-ink-3">{f.role}</span>
            <div className="mono break-all text-[11px] text-ink-3">{f.sha256}</div>
          </li>
        ))}</ul>
      </div>
      <div className="col-span-12 space-y-8 md:col-span-5">
        <div>
          <H>Transformations</H>
          <ul className="space-y-1 text-ink-2">{(man.transformations ?? []).map((t: string) => <li key={t} className="border-l border-rule-strong pl-3">{t}</li>)}</ul>
        </div>
        {(man.notes ?? []).length > 0 && (
          <div>
            <H>Notes</H>
            <ul className="space-y-1">{man.notes.map((t: string) => <li key={t} className="note note-warn">{t}</li>)}</ul>
          </div>
        )}
        <div>
          <H>Required citations</H>
          <ul className="space-y-1 text-ink-2">{(man.citations ?? []).map((c: { text: string }) => <li key={c.text} className="border-l border-rule-strong pl-3">{c.text}</li>)}</ul>
        </div>
        <p className="text-xs text-ink-3">Sign policy: {man.sign_policy_source}</p>
      </div>
    </div>
  );
}

function Sources({ data }: { data: Record<string, any> }) {  // eslint-disable-line @typescript-eslint/no-explicit-any
  return (
    <div className="space-y-12 text-sm">
      <ul className="border-t border-rule-strong">
        {data.bundles.map((b: Record<string, any>) => (  // eslint-disable-line @typescript-eslint/no-explicit-any
          <li key={b.key} className="grid gap-x-6 gap-y-2 border-b border-rule py-4 md:grid-cols-[13rem_1fr_minmax(0,24rem)]">
            <div className="font-medium">{b.title}</div>
            <div>
              <p className="text-ink-2">{b.description}</p>
              <p className="mt-1 text-xs text-ink-3">{b.files.length} file(s), {fmt.int(Math.round(b.files.reduce((s: number, f: { size_bytes: number | null }) => s + (f.size_bytes ?? 0), 0) / 1e6))} MB, checksummed</p>
            </div>
            <code className="mono block self-start overflow-x-auto whitespace-nowrap border-l-2 border-accent !bg-transparent py-1 pl-3 text-xs">{b.command}</code>
          </li>
        ))}
      </ul>
      <div className="max-w-[64ch]">
        <h3 className="mb-1 text-sm font-medium">FlyWire Codex downloads</h3>
        <p className="text-ink-2">{data.codex.note}</p>
        <a className="mono mt-1 inline-block break-all text-xs" href={data.codex.url} target="_blank" rel="noreferrer">{data.codex.url}</a>
      </div>
      <div>
        <h3 className="mb-3 text-sm font-medium">Dataset adapters</h3>
        <ul className="border-t border-rule">{data.adapters.map((a: Record<string, string>) => (
          <li key={a.name} className="grid grid-cols-[7rem_1fr] items-baseline gap-4 border-b border-rule py-2">
            <span className="inline-flex items-center gap-2"><span aria-hidden className="inline-block h-[7px] w-[7px]" style={{ background: a.status === "supported" ? "var(--ok)" : "var(--warn)" }} />{a.status}</span>
            <span>{a.title}<span className="text-ink-3"> — {a.description}</span></span>
          </li>
        ))}</ul>
      </div>
      <p className="max-w-[64ch] text-xs leading-5 text-ink-3">{data.license_note}</p>
    </div>
  );
}

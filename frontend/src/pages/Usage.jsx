import React, { useState } from 'react';
import { ChevronDown, Code2, Search } from 'lucide-react';
import { Disclosure, Empty, EvidenceLabel, Loc, Panel, Pill, Reveal, Tabs } from '../components/ui.jsx';
import { USAGE_STATUS } from '../lib/model.js';
import { hrefFor } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

export default function Usage({ params }) {
  const { view, runId, offline } = useWS();
  const [status, setStatus] = useState('all');
  const [q, setQ] = useState(params.pkg || '');
  const [open, setOpen] = useState(() => new Set(params.pkg ? [params.pkg] : []));
  const u = view.usage;
  if (!u) return <Empty icon={Code2} title="No usage tracing for this run">Usage tracing runs with every scan. Imported runs only show it when patchproof-usage-report.json was included.</Empty>;
  const by = u.summary?.by_status || {};
  const pkgs = view.packages.filter((p) => (status === 'all' || p.usage_status === status) && `${p.package} ${(p.imports_found || []).map((i) => i.file).join(' ')}`.toLowerCase().includes(q.toLowerCase().trim()));
  const toggle = (k) => setOpen((s) => { const n = new Set(s); if (n.has(k)) n.delete(k); else n.add(k); return n; });

  return (
    <>
      <Reveal i={0} className="usage-summary">
        {Object.entries(USAGE_STATUS).map(([k, m]) => (
          <button type="button" key={k} className={`usage-stat ${status === k ? 'active' : ''}`} onClick={() => setStatus(status === k ? 'all' : k)} aria-pressed={status === k}>
            <Pill tone={m.tone}>{m.label}</Pill><strong>{by[k] || 0}</strong>
          </button>
        ))}
        <div className="usage-stat static"><small>Python files traced</small><strong>{u.python_files_scanned ?? '—'}</strong></div>
      </Reveal>
      <Reveal i={1}>
        <div className="toolbar">
          <Tabs label="Usage status" value={status} onChange={setStatus} tabs={[{ value: 'all', label: 'All packages', count: view.packages.length }, ...Object.entries(USAGE_STATUS).filter(([k]) => by[k]).map(([k, m]) => ({ value: k, label: m.label, count: by[k] }))]} />
          <div className="search"><Search size={15} /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter packages or files" aria-label="Filter packages" /></div>
        </div>
      </Reveal>
      <Reveal i={2}>
        <Panel title="Package → import evidence" subtitle="Static AST tracing. Project code was never imported or executed.">
          {pkgs.length ? pkgs.map((p) => {
            const m = USAGE_STATUS[p.usage_status] || { tone: 'muted', label: p.usage_status };
            const isOpen = open.has(p.package);
            return (
              <article key={p.package} className={`pkg ${isOpen ? 'open' : ''}`}>
                <button type="button" className="pkg-main" onClick={() => toggle(p.package)} aria-expanded={isOpen}>
                  <span className="pkg-icon"><Code2 size={16} /></span>
                  <span className="pkg-text">
                    <strong>{p.package}</strong>
                    <small>{(p.declarations || []).map((d) => `${d.file}:${d.line ?? '?'} ${d.constraint || '(any)'}`).join(' · ') || 'No declaration details'}</small>
                  </span>
                  <span className="pkg-imports">{(p.imports_found || []).length} import{(p.imports_found || []).length === 1 ? '' : 's'}</span>
                  <Pill tone={m.tone}>{m.label}</Pill>
                  <ChevronDown size={16} className={`chev ${isOpen ? 'rot' : ''}`} />
                </button>
                {isOpen && (
                  <div className="pkg-detail">
                    <div className="pkg-cols">
                      <div>
                        <span className="obs-label">Declared in</span>
                        <ul className="plain-list">{(p.declarations || []).map((d, i) => <li key={i}><Loc file={d.file} line={d.line} /> <code>{d.constraint || '(any version)'}</code> <span className="muted small">{d.section}</span></li>)}</ul>
                      </div>
                      <div>
                        <span className="obs-label">Imports found <EvidenceLabel label="OBSERVED" /></span>
                        {(p.imports_found || []).length ? (
                          <ul className="import-list">{p.imports_found.map((i, k) => <li key={k}><Loc file={i.file} line={i.line} /><code>{i.statement || i.module}</code>{i.kind === 'dynamic_literal' && <Pill tone="warn">dynamic</Pill>}</li>)}</ul>
                        ) : <p className="muted small">No static import matched {(p.candidate_import_roots || []).map((r) => <code key={r}>{r}</code>)}.</p>}
                      </div>
                    </div>
                    <p className="interp"><strong>Interpretation:</strong> {p.interpretation}</p>
                    <p className="muted small">Import roots {p.mapping_source === 'installed_metadata' ? 'from installed distribution metadata' : 'guessed from the distribution name (package not installed where the tracer ran)'}: {(p.candidate_import_roots || []).join(', ') || '—'}</p>
                    {p.review_lead_id && <a className="related-link" href={hrefFor('findings', { run: offline ? undefined : runId, id: p.review_lead_id })}><EvidenceLabel label="OBSERVED" /> Review lead {p.review_lead_id}</a>}
                  </div>
                )}
              </article>
            );
          }) : <Empty icon={Search} title="No packages match" compact>Clear the filter to see all {view.packages.length} packages.</Empty>}
        </Panel>
      </Reveal>
      <div className="two-col">
        <Reveal i={3}>
          <Panel title="Parse errors and dynamic imports" subtitle="Places static tracing could not fully see">
            <div className="panel-pad">
              {(u.parse_errors || []).length ? <ul className="plain-list">{u.parse_errors.map((e, i) => <li key={i}><Loc file={e.file} line={e.line} /> {e.error || e.message}</li>)}</ul> : <p className="muted small">No Python files failed to parse.</p>}
              {Object.keys(u.unresolved_dynamic_imports || {}).length > 0 && (
                <Disclosure summary="Unresolved dynamic imports">
                  <ul className="plain-list">{Object.entries(u.unresolved_dynamic_imports).map(([f, n]) => <li key={f}><code>{f}</code>: {n}</li>)}</ul>
                </Disclosure>
              )}
            </div>
          </Panel>
        </Reveal>
        <Reveal i={4}>
          <Panel title="Interpretation notes" subtitle="Read before acting on a lead">
            <ul className="plain-list panel-pad">{(u.limitations || []).map((l, i) => <li key={i}>{l}</li>)}</ul>
          </Panel>
        </Reveal>
      </div>
    </>
  );
}

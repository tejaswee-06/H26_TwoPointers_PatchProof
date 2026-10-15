import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Activity, ChevronDown, CircleAlert, Download, FileCode2, HelpCircle, Mic, Search, Volume2 } from 'lucide-react';
import { CopyButton, Disclosure, Empty, EvidenceLabel, Loc, Panel, Pill, Reveal, Tabs } from '../components/ui.jsx';
import { saveBlob } from '../lib/api.js';
import { hrefFor } from '../lib/router.js';
import { useWS } from '../lib/workspace.js';

const SEV_ICON = { high: CircleAlert, review: Activity, info: HelpCircle };

function FindingCard({ f, open, onToggle, related, runId, speak }) {
  const Icon = SEV_ICON[f.severity] || CircleAlert;
  const ref = useRef(null);
  useEffect(() => { if (open && ref.current?.dataset.deeplink === 'true') ref.current.scrollIntoView({ block: 'center' }); }, [open]);
  return (
    <article className={`finding ${open ? 'open' : ''}`} id={f.id ? `ev-${f.id}` : undefined} ref={ref} data-deeplink={open ? 'true' : 'false'}>
      <button type="button" className="finding-main" onClick={onToggle} aria-expanded={open}>
        <span className={`sev-icon sev-${f.severity}`}><Icon size={16} /></span>
        <span className="finding-text">
          <strong>{f.title}</strong>
          <small><code>{f.id || 'no id'}</code> · {f.kind === 'lead' ? 'usage review lead' : f.type.replaceAll('_', ' ')}{f.package ? ` · ${f.package}` : ''}</small>
        </span>
        <span className="finding-pills">
          <Pill tone={f.severity === 'high' ? 'bad' : f.severity === 'review' ? 'warn' : 'muted'}>{f.severity}</Pill>
          <EvidenceLabel label="OBSERVED" />
        </span>
        <ChevronDown size={16} className={`chev ${open ? 'rot' : ''}`} />
      </button>
      {open && (
        <div className="finding-detail">
          {f.summary && <p>{f.summary}</p>}
          {(f.observed || f.inferred) && (
            <div className="obs-inf">
              {f.observed && <div className="obs"><span className="obs-label">Observed</span><p>{f.observed}</p></div>}
              {f.inferred && <div className="inf"><span className="obs-label">Inferred from the comparison</span><p>{f.inferred}</p></div>}
            </div>
          )}
          {f.evidence.length > 0 ? (
            <div className="evidence-list">
              {f.evidence.map((e, i) => (
                <div className="evidence-block" key={i}>
                  <div className="evidence-head"><FileCode2 size={14} /><Loc file={e.file} line={e.line} />{e.section && <span className="muted small">{e.section}</span>}{e.role && <Pill tone="muted">{e.role}</Pill>}</div>
                  <code className="evidence-code">{e.excerpt || '(no excerpt recorded)'}</code>
                  {(e.specifier || e.marker) && <small className="muted">specifier <code>{e.specifier || '(any)'}</code>{e.marker ? <> · marker <code>{e.marker}</code></> : null}</small>}
                </div>
              ))}
            </div>
          ) : f.kind === 'lead' ? (
            <p className="muted small">Usage leads are based on static import tracing. <a href={hrefFor('usage', { run: runId, pkg: f.package })}>Inspect {f.package} in usage tracing</a>.</p>
          ) : <p className="muted small">The artifact recorded no source evidence for this finding.</p>}
          {f.pairs?.length > 0 && (
            <Disclosure summary={`${f.pairs.length} pairwise comparison${f.pairs.length === 1 ? '' : 's'}`}>
              <ul className="plain-list">{f.pairs.map((p, i) => <li key={i}><code>{p.a}</code> vs <code>{p.b}</code>: <strong>{p.assessment}</strong> — {p.reason}</li>)}</ul>
            </Disclosure>
          )}
          {related.length > 0 && (
            <div className="related">
              <span className="obs-label">Referenced by</span>
              {related.map((r) => <a key={r.key} href={r.href} className="related-link"><EvidenceLabel label={r.label} /> {r.text}</a>)}
            </div>
          )}
          <div className="finding-actions">
            {f.id && <CopyButton text={f.id} label="Copy ID" />}
            <button type="button" className="ghost-btn" onClick={() => saveBlob(`${f.id || 'finding'}.json`, JSON.stringify(f.raw, null, 2))}><Download size={14} /> Export JSON</button>
            <button type="button" className="ghost-btn" onClick={() => speak(`${f.title}. ${f.summary}`)}><Volume2 size={14} /> Read aloud</button>
          </div>
        </div>
      )}
    </article>
  );
}

export default function Findings({ params }) {
  const { view, runId, speak, toast, offline } = useWS();
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('all');
  const [sev, setSev] = useState(params.severity || 'all');
  const [openIds, setOpenIds] = useState(() => new Set(params.id ? [params.id] : []));
  const [listening, setListening] = useState(false);
  const rec = useRef(null);
  const rid = offline ? undefined : runId;

  const related = useMemo(() => {
    const map = {};
    for (const c of view.candidates) for (const id of c.related_ids || []) (map[id] ||= []).push({ key: c.id, label: 'HYPOTHESIS', text: c.title, href: hrefFor('root-cause', { run: rid, id: c.id }) });
    if (view.ai) for (const id of view.ai.finding_ids || []) (map[id] ||= []).push({ key: `ai-${id}`, label: 'AI PROPOSAL', text: `Gemma 4 analysis (${view.ai.model})`, href: hrefFor('migration', { run: rid }) });
    return map;
  }, [view, rid]);

  const list = view.all.filter((f) => (kind === 'all' || f.kind === kind) && (sev === 'all' || f.severity === sev)
    && `${f.id} ${f.title} ${f.summary} ${f.package} ${f.type} ${f.evidence.map((e) => `${e.file} ${e.excerpt}`).join(' ')}`.toLowerCase().includes(query.toLowerCase().trim()));

  function voice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast('Speech recognition is not supported in this browser. Type in the search box instead.', 'warn'); return; }
    if (listening) { rec.current?.stop(); setListening(false); return; }
    const r = new SR(); rec.current = r; r.lang = navigator.language || 'en-US'; r.interimResults = false;
    r.onresult = (e) => { const t = e.results[0][0].transcript; setQuery(t); toast(`Voice search: “${t}”`); };
    r.onerror = () => toast('Microphone input failed or permission was denied', 'warn');
    r.onend = () => setListening(false);
    r.start(); setListening(true);
  }
  const toggle = (id) => setOpenIds((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const scan = view.scan;

  return (
    <>
      <Reveal i={0}>
        <div className="toolbar">
          <Tabs label="Evidence kind" value={kind} onChange={setKind} tabs={[
            { value: 'all', label: 'All', count: view.all.length },
            { value: 'finding', label: 'Manifest findings', count: view.findings.length },
            { value: 'lead', label: 'Usage leads', count: view.leads.length }]} />
          <div className="toolbar-right">
            <label className="select-wrap"><span className="sr-only">Severity</span>
              <select value={sev} onChange={(e) => setSev(e.target.value)}>
                <option value="all">All severities</option><option value="high">High</option><option value="review">Review</option><option value="info">Info</option>
              </select>
            </label>
            <div className="search">
              <Search size={15} />
              <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search IDs, packages, files" aria-label="Search findings" />
              <button type="button" onClick={voice} aria-label={listening ? 'Stop voice search' : 'Search by voice'} data-active={listening}><Mic size={14} /></button>
            </div>
          </div>
        </div>
      </Reveal>
      <Reveal i={1}>
        <Panel title={`${list.length} of ${view.all.length} items`} subtitle="Severity 'review' means worth a human look — it is not a vulnerability rating"
          actions={list.length > 0 && <button type="button" className="ghost-btn" onClick={() => setOpenIds(openIds.size ? new Set() : new Set(list.map((f) => f.id)))}>{openIds.size ? 'Collapse all' : 'Expand all'}</button>}>
          {list.length ? list.map((f, i) => (
            <FindingCard key={f.id || i} f={f} open={openIds.has(f.id)} onToggle={() => toggle(f.id)} related={related[f.id] || []} runId={rid} speak={speak} />
          )) : (
            <Empty icon={Search} title={view.all.length ? 'Nothing matches these filters' : scan ? 'No findings in this scan' : 'No scan evidence loaded'} compact
              actions={view.all.length ? <button type="button" className="button button-outline button-small" onClick={() => { setQuery(''); setKind('all'); setSev('all'); }}>Clear filters</button> : null}>
              {view.all.length ? 'Try another search or clear the filters.' : scan?.scan_status === 'no_manifests_found' ? 'No supported manifests were found, so the repository was not assessed. That is not the same as a clean result.' : 'The scanner reported no manifest inconsistencies and the usage tracer reported no review leads.'}
            </Empty>
          )}
        </Panel>
      </Reveal>
      {scan && (
        <div className="two-col">
          <Reveal i={2}>
            <Panel title="Manifests scanned" subtitle={`Scan status: ${scan.scan_status}`}>
              <ul className="kv-list">
                {(scan.manifests || []).map((m) => <li key={m.file}><Loc file={m.file} /><span>{m.format}</span><strong>{m.declaration_count} declarations</strong></li>)}
                {!(scan.manifests || []).length && <li className="muted">No manifests.</li>}
              </ul>
              {(scan.errors || []).length > 0 && (
                <div className="panel-pad">
                  <span className="obs-label">Parse and read messages</span>
                  <ul className="plain-list">{scan.errors.map((e, i) => <li key={i}><Pill tone={e.severity === 'error' || !e.severity ? 'bad' : e.severity === 'warning' ? 'warn' : 'muted'}>{e.severity || 'error'}</Pill> <Loc file={e.file} line={e.line} /> {e.error}</li>)}</ul>
                </div>
              )}
            </Panel>
          </Reveal>
          <Reveal i={3}>
            <Panel title="Scanner limitations" subtitle="What this scan cannot see">
              <ul className="plain-list panel-pad">{(scan.limitations || []).map((l, i) => <li key={i}>{typeof l === 'string' ? l : JSON.stringify(l)}</li>)}</ul>
              {scan.exclusions?.excluded_directories_encountered?.length > 0 && (
                <Disclosure summary={`${scan.exclusions.excluded_directories_encountered.length} excluded director${scan.exclusions.excluded_directories_encountered.length === 1 ? 'y' : 'ies'}`} className="panel-pad">
                  <ul className="plain-list">{scan.exclusions.excluded_directories_encountered.map((e) => <li key={e.path}><code>{e.path}</code> — {e.reason.replaceAll('_', ' ')}</li>)}</ul>
                </Disclosure>
              )}
            </Panel>
          </Reveal>
        </div>
      )}
    </>
  );
}

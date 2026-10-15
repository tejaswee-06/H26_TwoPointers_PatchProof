import React, { useEffect, useState } from 'react';
import { AlertTriangle, Check, CircleDashed, Loader2, MinusCircle, X } from 'lucide-react';
import { api } from '../lib/api.js';
import { useWS } from '../lib/workspace.js';

const ICON = { done: Check, warn: AlertTriangle, failed: X, cancelled: MinusCircle, skipped: MinusCircle, running: Loader2, pending: CircleDashed };

function useElapsed(start, running) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (!running) return undefined;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  if (!start) return null;
  const s = Math.max(0, Math.round(((running ? now : Date.now()) - new Date(start).getTime()) / 1000));
  return s < 60 ? `${s}s` : `${Math.floor(s / 60)}m ${s % 60}s`;
}

export default function JobProgress({ job, title, children }) {
  const { toast } = useWS();
  const [cancelling, setCancelling] = useState(false);
  const active = ['queued', 'running'].includes(job.state);
  const elapsed = useElapsed(job.started_at || job.created_at, active);
  async function cancel() {
    setCancelling(true);
    try { await api.cancelJob(job.id); toast('Cancellation requested', 'warn'); } catch (e) { toast(e.message, 'bad'); }
  }
  return (
    <div className={`job-progress job-${job.state}`} aria-live="polite">
      <div className="job-progress-head">
        <div>
          <strong>{title}</strong>
          <small>{active ? `Running · ${elapsed ?? ''}` : job.state === 'succeeded' ? `Finished in ${elapsed}` : job.state === 'cancelled' ? 'Cancelled' : 'Failed'}</small>
        </div>
        {active && <button type="button" className="button button-outline button-small" onClick={cancel} disabled={cancelling || job.cancel_requested}>{cancelling || job.cancel_requested ? 'Cancelling…' : 'Cancel'}</button>}
      </div>
      <ol className="stepper">
        {job.stages.map((s, i) => {
          const Icon = ICON[s.state] || CircleDashed;
          return (
            <li key={s.key} className={`step step-${s.state}`} style={{ '--i': i }}>
              <span className="step-icon"><Icon size={13} className={s.state === 'running' ? 'spin' : ''} /></span>
              <div><strong>{s.label}</strong>{s.detail && <small>{s.detail}</small>}</div>
            </li>
          );
        })}
      </ol>
      {job.error && <p className="job-error"><AlertTriangle size={14} /> {job.error}</p>}
      {children}
    </div>
  );
}

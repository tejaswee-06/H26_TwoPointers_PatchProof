import React from 'react';
import { AlertTriangle, Check, CircleDashed, Sparkles, X } from 'lucide-react';

const STATE_TEXT = { done: 'Ready', warn: 'Review', bad: 'Failed', pending: 'Pending', missing: 'Missing', empty: 'None found', proposal: 'Proposal' };
const STATE_ICON = { done: Check, warn: AlertTriangle, bad: X, proposal: Sparkles };

// The evidence chain: scan → diagnose → Gemma 4 → verify → capsule, with honest per-stage states.
export default function Pipeline({ stages, onSelect, compact }) {
  return (
    <ol className={`pipeline ${compact ? 'pipeline-compact' : ''}`} aria-label="Evidence chain">
      {stages.map((s, i) => {
        const Icon = STATE_ICON[s.state] || CircleDashed;
        const Tag = onSelect ? 'button' : 'div';
        return (
          <li key={s.key} className={`pipe-step state-${s.state}`} style={{ '--i': i }}>
            <Tag type={onSelect ? 'button' : undefined} className="pipe-node" onClick={onSelect ? () => onSelect(s) : undefined}>
              <span className="pipe-icon"><Icon size={15} /></span>
              <span className="pipe-text">
                <strong>{s.label}</strong>
                <small>{s.detail}</small>
              </span>
              <span className="pipe-state">{STATE_TEXT[s.state] || s.state}</span>
            </Tag>
            {i < stages.length - 1 && <span className="pipe-link" aria-hidden="true" />}
          </li>
        );
      })}
    </ol>
  );
}

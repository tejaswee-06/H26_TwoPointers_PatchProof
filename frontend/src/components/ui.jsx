import React, { useEffect, useId, useRef, useState } from 'react';
import { Check, ChevronDown, ChevronRight, Copy, X } from 'lucide-react';
import { EVIDENCE_LABELS, VERIFICATION_STATUS } from '../lib/model.js';

export function Pill({ tone = 'muted', children, title, className = '' }) {
  return <span className={`pill tone-${tone} ${className}`} title={title}>{children}</span>;
}

export function EvidenceLabel({ label, className }) {
  const meta = EVIDENCE_LABELS[label] || { tone: 'muted', hint: '' };
  return <Pill tone={meta.tone} title={meta.hint} className={`evidence-label ${className || ''}`}>{label === 'NOT_RUN' ? 'Not run' : label}</Pill>;
}

export function VerificationBadge({ status, large }) {
  const m = VERIFICATION_STATUS[status] || VERIFICATION_STATUS.NOT_RUN;
  return <Pill tone={m.tone} title={m.meaning} className={large ? 'pill-large' : ''}><span className="dot" />{status || 'NOT_RUN'}</Pill>;
}

export function Panel({ title, subtitle, actions, children, className = '', id, as: Tag = 'section', style }) {
  const hid = useId();
  return (
    <Tag className={`panel ${className}`} id={id} aria-labelledby={title ? hid : undefined} style={style}>
      {(title || actions) && (
        <header className="panel-head">
          <div>
            {title && <h3 id={hid}>{title}</h3>}
            {subtitle && <p>{subtitle}</p>}
          </div>
          {actions && <div className="panel-actions">{actions}</div>}
        </header>
      )}
      {children}
    </Tag>
  );
}

export function Empty({ icon: Icon, title, children, actions, compact }) {
  return (
    <div className={`empty ${compact ? 'empty-compact' : ''}`}>
      {Icon && <div className="empty-icon"><Icon size={22} /></div>}
      <strong>{title}</strong>
      {children && <div className="empty-body">{children}</div>}
      {actions && <div className="empty-actions">{actions}</div>}
    </div>
  );
}

export function Skeleton({ lines = 3, height }) {
  return (
    <div className="skeleton" aria-hidden="true" style={height ? { height } : undefined}>
      {Array.from({ length: lines }).map((_, i) => <span key={i} style={{ width: `${92 - i * 13}%` }} />)}
    </div>
  );
}

export function Metric({ icon: Icon, label, value, note, tone, onClick }) {
  const Tag = onClick ? 'button' : 'div';
  return (
    <Tag className={`metric ${onClick ? 'is-link' : ''}`} onClick={onClick} type={onClick ? 'button' : undefined}>
      <span className="metric-top">{label}{Icon && <Icon size={16} />}</span>
      <strong className={tone ? `tone-text-${tone}` : ''}>{value}</strong>
      {note && <small>{note}</small>}
    </Tag>
  );
}

export function CopyButton({ text, label = 'Copy', className = '', onCopied }) {
  const [done, setDone] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const ta = document.createElement('textarea');
      ta.value = text; document.body.appendChild(ta); ta.select();
      try { document.execCommand('copy'); } catch { /* ignore */ }
      ta.remove();
    }
    setDone(true); onCopied?.();
    setTimeout(() => setDone(false), 1400);
  }
  return (
    <button type="button" className={`ghost-btn ${className}`} onClick={copy} aria-label={`${label}: ${String(text).slice(0, 40)}`}>
      {done ? <Check size={14} /> : <Copy size={14} />}<span>{done ? 'Copied' : label}</span>
    </button>
  );
}

export function Disclosure({ summary, children, defaultOpen = false, className = '' }) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className={`disclosure ${open ? 'open' : ''} ${className}`}>
      <button type="button" className="disclosure-btn" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <ChevronRight size={15} className="chev" />{summary}
      </button>
      {open && <div id={id} className="disclosure-body">{children}</div>}
    </div>
  );
}

export function CodeBlock({ children, label, maxHeight = 320, copy = true }) {
  const text = String(children ?? '');
  return (
    <div className="codeblock">
      {(label || copy) && (
        <div className="codeblock-head">
          <span>{label}</span>
          {copy && text && <CopyButton text={text} />}
        </div>
      )}
      <pre style={{ maxHeight }} tabIndex={0}>{text || '(empty)'}</pre>
    </div>
  );
}

function JsonNode({ k, v, depth }) {
  const [open, setOpen] = useState(depth < 1);
  const isObj = v && typeof v === 'object';
  if (!isObj) {
    const cls = v === null ? 'j-null' : typeof v === 'string' ? 'j-str' : typeof v === 'number' ? 'j-num' : 'j-bool';
    const shown = typeof v === 'string' ? JSON.stringify(v.length > 600 ? `${v.slice(0, 600)}…` : v) : String(v);
    return <div className="j-row">{k != null && <span className="j-key">{k}: </span>}<span className={cls}>{shown}</span></div>;
  }
  const entries = Array.isArray(v) ? v.map((x, i) => [i, x]) : Object.entries(v);
  return (
    <div className="j-row">
      <button type="button" className="j-toggle" onClick={() => setOpen(!open)} aria-expanded={open}>
        <ChevronDown size={12} className={open ? '' : 'rot'} />
        {k != null && <span className="j-key">{k}: </span>}
        <span className="j-meta">{Array.isArray(v) ? `[${entries.length}]` : `{${entries.length}}`}</span>
      </button>
      {open && <div className="j-children">{entries.map(([ck, cv]) => <JsonNode key={ck} k={ck} v={cv} depth={depth + 1} />)}</div>}
    </div>
  );
}

export function JsonTree({ data }) {
  return <div className="json-tree" tabIndex={0}><JsonNode k={null} v={data} depth={0} /></div>;
}

export function Tabs({ tabs, value, onChange, label }) {
  const refs = useRef([]);
  function onKey(e, i) {
    if (!['ArrowRight', 'ArrowLeft', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    let n = i;
    if (e.key === 'ArrowRight') n = (i + 1) % tabs.length;
    if (e.key === 'ArrowLeft') n = (i - 1 + tabs.length) % tabs.length;
    if (e.key === 'Home') n = 0;
    if (e.key === 'End') n = tabs.length - 1;
    onChange(tabs[n].value); refs.current[n]?.focus();
  }
  return (
    <div className="tabs" role="tablist" aria-label={label}>
      {tabs.map((t, i) => (
        <button key={t.value} ref={(el) => { refs.current[i] = el; }} role="tab" type="button" aria-selected={value === t.value}
          tabIndex={value === t.value ? 0 : -1} className={value === t.value ? 'active' : ''}
          onClick={() => onChange(t.value)} onKeyDown={(e) => onKey(e, i)}>
          {t.icon && <t.icon size={14} />}{t.label}{t.count != null && <span className="tab-count">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Modal({ title, onClose, children, footer, wide }) {
  const ref = useRef(null);
  useEffect(() => {
    const prev = document.activeElement;
    ref.current?.querySelector('input,button,select,textarea,[tabindex]')?.focus();
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Tab' && ref.current) {
        const f = [...ref.current.querySelectorAll('button,input,select,textarea,a[href],[tabindex]:not([tabindex="-1"])')].filter((x) => !x.disabled);
        if (!f.length) return;
        if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f[f.length - 1].focus(); }
        else if (!e.shiftKey && document.activeElement === f[f.length - 1]) { e.preventDefault(); f[0].focus(); }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => { document.removeEventListener('keydown', onKey); prev?.focus?.(); };
  }, [onClose]);
  return (
    <div className="modal-backdrop" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className={`modal ${wide ? 'modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header className="modal-head"><h2>{title}</h2><button type="button" className="icon-btn" onClick={onClose} aria-label="Close"><X size={16} /></button></header>
        <div className="modal-body">{children}</div>
        {footer && <footer className="modal-foot">{footer}</footer>}
      </div>
    </div>
  );
}

export function Loc({ file, line }) {
  if (!file) return null;
  return <code className="loc">{file}{line != null ? `:${line}` : ''}</code>;
}

export function Reveal({ i = 0, children, className = '', as: Tag = 'div', ...rest }) {
  return <Tag className={`reveal ${className}`} style={{ '--i': i }} {...rest}>{children}</Tag>;
}

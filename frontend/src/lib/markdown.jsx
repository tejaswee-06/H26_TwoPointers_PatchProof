import React from 'react';

// Safe renderer for the Markdown subset produced by patchproof.capsule.to_markdown:
// headings, bullet lists (with one nesting level), paragraphs, **bold** and `code`.
// Produces React elements only — no HTML injection.
function inline(text, keyBase) {
  const parts = [];
  const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
  let last = 0; let m; let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const tok = m[0];
    parts.push(tok.startsWith('`')
      ? <code key={`${keyBase}-${i++}`}>{tok.slice(1, -1)}</code>
      : <strong key={`${keyBase}-${i++}`}>{tok.slice(2, -2)}</strong>);
    last = m.index + tok.length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// Inline `code` and **bold** inside engine-generated sentences (no HTML injection).
export function RichText({ text }) {
  return <>{inline(String(text ?? ''), 'rt')}</>;
}

export function Markdown({ source }) {
  const lines = String(source || '').split('\n');
  const blocks = [];
  let list = null;
  const flush = () => { if (list) { blocks.push(list); list = null; } };
  lines.forEach((raw, idx) => {
    const line = raw.replace(/\s+$/, '');
    if (!line.trim()) { flush(); return; }
    const h = /^(#{1,4})\s+(.*)$/.exec(line);
    if (h) { flush(); blocks.push({ type: `h${h[1].length}`, text: h[2], idx }); return; }
    const li = /^(\s*)-\s+(.*)$/.exec(line);
    if (li) {
      if (!list) list = { type: 'ul', items: [], idx };
      const nested = li[1].length >= 2 && list.items.length;
      if (nested) (list.items[list.items.length - 1].children ||= []).push(li[2]);
      else list.items.push({ text: li[2] });
      return;
    }
    flush();
    blocks.push({ type: 'p', text: line, idx });
  });
  flush();
  return (
    <div className="md">
      {blocks.map((b) => {
        if (b.type === 'ul') {
          return (
            <ul key={b.idx}>
              {b.items.map((it, j) => (
                <li key={j}>{inline(it.text, `${b.idx}-${j}`)}
                  {it.children && <ul>{it.children.map((c, k) => <li key={k}>{inline(c, `${b.idx}-${j}-${k}`)}</li>)}</ul>}
                </li>
              ))}
            </ul>
          );
        }
        const Tag = b.type === 'p' ? 'p' : b.type;
        return <Tag key={b.idx}>{inline(b.text, b.idx)}</Tag>;
      })}
    </div>
  );
}

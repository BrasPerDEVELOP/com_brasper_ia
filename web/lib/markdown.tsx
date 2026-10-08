import React from "react";

// Renderizador Markdown mínimo y seguro (sin HTML ejecutable): títulos, párrafos,
// listas, negrita, cursiva y enlaces http(s). Todo lo demás se muestra como texto.
const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\((https?:\/\/[^\s)]+)\))/g;

function inline(text: string, key: string): React.ReactNode[] {
  const out: React.ReactNode[] = [];
  let last = 0, i = 0;
  for (const m of text.matchAll(INLINE)) {
    const idx = m.index ?? 0;
    if (idx > last) out.push(text.slice(last, idx));
    const tok = m[0];
    if (tok.startsWith("**")) out.push(<strong key={`${key}-${i++}`}>{tok.slice(2, -2)}</strong>);
    else if (tok.startsWith("[")) {
      const label = tok.slice(1, tok.indexOf("]"));
      out.push(<a key={`${key}-${i++}`} href={m[2]} target="_blank" rel="noopener noreferrer">{label}</a>);
    } else out.push(<em key={`${key}-${i++}`}>{tok.slice(1, -1)}</em>);
    last = idx + tok.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export function Markdown({ text }: { text: string }) {
  const lines = (text || "").replace(/\r\n/g, "\n").split("\n");
  const blocks: React.ReactNode[] = [];
  let para: string[] = [];
  let list: string[] = [];
  let ordered = false;
  const flushPara = () => { if (para.length) { blocks.push(<p key={`p${blocks.length}`}>{inline(para.join(" "), `p${blocks.length}`)}</p>); para = []; } };
  const flushList = () => {
    if (!list.length) return;
    const items = list.map((l, i) => <li key={i}>{inline(l, `l${blocks.length}-${i}`)}</li>);
    blocks.push(ordered ? <ol key={`o${blocks.length}`}>{items}</ol> : <ul key={`u${blocks.length}`}>{items}</ul>);
    list = [];
  };
  for (const raw of lines) {
    const line = raw.trimEnd();
    const h = /^(#{1,3})\s+(.*)$/.exec(line);
    const ul = /^[-*]\s+(.*)$/.exec(line);
    const ol = /^\d+[.)]\s+(.*)$/.exec(line);
    if (!line.trim()) { flushPara(); flushList(); continue; }
    if (h) {
      flushPara(); flushList();
      const Tag = (`h${h[1].length + 1}`) as "h2" | "h3" | "h4";
      blocks.push(<Tag key={`h${blocks.length}`}>{inline(h[2], `h${blocks.length}`)}</Tag>);
      continue;
    }
    if (ul || ol) {
      flushPara();
      if (list.length && ordered !== !!ol) flushList();
      ordered = !!ol;
      list.push((ul || ol)![1]);
      continue;
    }
    flushList();
    para.push(line.trim());
  }
  flushPara(); flushList();
  return <div className="md">{blocks}</div>;
}

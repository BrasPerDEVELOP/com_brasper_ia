"use client";
import { useEffect, useMemo, useState } from "react";
import { api, UsageDay, UsageRow } from "@/lib/api";
import Icon from "@/components/Icon";

interface Ev { created_at: string; conversation_id: string; model: string; tokens_in: number; tokens_out: number; cost_usd: number; }
const PAGE = 20;
const fmtInt = (n: number) => Number(n || 0).toLocaleString("es");
const fmtUsd = (n: number, d = 4) => "US$ " + Number(n || 0).toLocaleString("es", { minimumFractionDigits: d, maximumFractionDigits: d });

/** Columnas de costo por día: una sola tonalidad (magnitud), barras finas con
    extremo redondeado, base común, grilla recesiva, tooltip al pasar. */
function DailyChart({ days }: { days: UsageDay[] }) {
  const [hover, setHover] = useState<number | null>(null);
  const data = useMemo(() => [...days].sort((a, b) => (a.day < b.day ? -1 : 1)).slice(-30), [days]);
  if (!data.length) return <div className="empty" style={{ padding: 28 }}>Sin consumo en los últimos días.</div>;
  const W = 720, H = 220, PL = 56, PR = 12, PT = 14, PB = 34;
  const iw = W - PL - PR, ih = H - PT - PB;
  const max = Math.max(...data.map(d => d.cost_usd), 0.000001);
  // Ticks "limpios": 4 divisiones redondeadas.
  const step = Math.pow(10, Math.floor(Math.log10(max / 4)));
  const nice = Math.ceil(max / 4 / step) * step;
  const top = nice * 4;
  const slot = iw / data.length;
  const bw = Math.min(24, Math.max(6, slot - 2));
  const y = (v: number) => PT + ih - (v / top) * ih;
  const label = (d: string) => d.slice(5).replace("-", "/");
  return (
    <div className="chart-wrap">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Costo diario en dólares, últimos 30 días">
        {[0, 1, 2, 3, 4].map(i => {
          const v = nice * i; const yy = y(v);
          return (
            <g key={i}>
              <line x1={PL} x2={W - PR} y1={yy} y2={yy} className="grid" />
              <text x={PL - 8} y={yy + 4} textAnchor="end" className="tick">{v === 0 ? "0" : v.toFixed(v < 0.01 ? 4 : 3)}</text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const x = PL + i * slot + (slot - bw) / 2;
          const h = Math.max(0, y(0) - y(d.cost_usd));
          const r = Math.min(4, bw / 2, h);
          const on = hover === i;
          const path = h <= 0 ? "" : `M${x},${y(0)} v${-(h - r)} a${r},${r} 0 0 1 ${r},${-r} h${bw - 2 * r} a${r},${r} 0 0 1 ${r},${r} v${h - r} z`;
          return (
            <g key={d.day} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <rect x={PL + i * slot} y={PT} width={slot} height={ih} fill="transparent" />
              {path && <path d={path} className={"bar" + (on ? " on" : "")} />}
              {(data.length <= 12 || i % Math.ceil(data.length / 10) === 0 || on) && (
                <text x={x + bw / 2} y={H - PB + 16} textAnchor="middle" className={"tick" + (on ? " on" : "")}>{label(d.day)}</text>
              )}
              {on && (
                <g>
                  <rect x={Math.min(W - PR - 150, Math.max(PL, x + bw / 2 - 75))} y={Math.max(0, y(d.cost_usd) - 46)} width={150} height={40} rx={8} className="tip" />
                  <text x={Math.min(W - PR - 150, Math.max(PL, x + bw / 2 - 75)) + 10} y={Math.max(0, y(d.cost_usd) - 46) + 16} className="tipt">{d.day} · {d.calls} llamadas</text>
                  <text x={Math.min(W - PR - 150, Math.max(PL, x + bw / 2 - 75)) + 10} y={Math.max(0, y(d.cost_usd) - 46) + 32} className="tipt b">{fmtUsd(d.cost_usd)}</text>
                </g>
              )}
            </g>
          );
        })}
        <line x1={PL} x2={W - PR} y1={y(0)} y2={y(0)} className="axis" />
      </svg>
    </div>
  );
}

export default function Consumo() {
  const [summary, setSummary] = useState<UsageRow[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [daily, setDaily] = useState<UsageDay[]>([]);
  const [err, setErr] = useState("");
  const [page, setPage] = useState(0);
  const [view, setView] = useState<"chart" | "table">("chart");

  useEffect(() => {
    api<{ summary: UsageRow[]; events: Ev[] }>("/api/usage?limit=500").then(d => { setSummary(d.summary); setEvents(d.events); }).catch(e => setErr((e as Error).message));
    api<{ daily: UsageDay[] }>("/api/ops/usage-daily").then(d => setDaily(d.daily)).catch(() => {});
  }, []);

  const tot = summary[0] || { calls: 0, tokens_in: 0, tokens_out: 0, cost_usd: 0 };
  const today = new Date().toISOString().slice(0, 10);
  const todayRow = daily.find(d => d.day === today);
  const avg = tot.calls ? tot.cost_usd / tot.calls : 0;
  const pages = Math.max(1, Math.ceil(events.length / PAGE));
  const slice = events.slice(page * PAGE, page * PAGE + PAGE);

  if (err) return <div className="usage-note err"><Icon name="alert" size={16} /> {err}</div>;
  return (
    <>
      <div className="stats">
        <div className="stat"><div className="ic ic-blue"><Icon name="chat" /></div><div className="num">{fmtInt(tot.calls)}</div><div className="lbl">Llamadas al LLM</div></div>
        <div className="stat"><div className="ic ic-green"><Icon name="coins" /></div><div className="num">{fmtUsd(tot.cost_usd, 2)}</div><div className="lbl">Costo acumulado · hoy {fmtUsd(todayRow?.cost_usd || 0, 3)}</div></div>
        <div className="stat"><div className="ic ic-amber"><Icon name="chart" /></div><div className="num">{fmtInt(tot.tokens_in)} <span className="muted" style={{ fontSize: 14 }}>→</span> {fmtInt(tot.tokens_out)}</div><div className="lbl">Tokens entrada → salida</div></div>
        <div className="stat"><div className="ic ic-coral"><Icon name="zap" /></div><div className="num">{fmtUsd(avg, 5)}</div><div className="lbl">Costo medio por llamada</div></div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head" style={{ marginBottom: 6 }}>
          <div>
            <h3>Costo diario</h3>
            <div className="muted" style={{ fontSize: 12.5 }}>Últimos 30 días con consumo. Cotizaciones, onboarding y handoff no gastan LLM.</div>
          </div>
          <div className="seg" role="tablist">
            <button role="tab" aria-selected={view === "chart"} className={view === "chart" ? "on" : ""} onClick={() => setView("chart")}>Gráfico</button>
            <button role="tab" aria-selected={view === "table"} className={view === "table" ? "on" : ""} onClick={() => setView("table")}>Tabla</button>
          </div>
        </div>
        {view === "chart" ? <DailyChart days={daily} /> : (
          <table><thead><tr><th>Día</th><th className="num">Llamadas</th><th className="num">Tokens in</th><th className="num">Tokens out</th><th className="num">Costo (US$)</th></tr></thead>
            <tbody>{daily.length ? daily.slice(0, 30).map(d => (
              <tr key={d.day}><td className="mono">{d.day}</td><td className="num">{fmtInt(d.calls)}</td><td className="num">{fmtInt(d.tokens_in)}</td><td className="num">{fmtInt(d.tokens_out)}</td><td className="num">{d.cost_usd.toFixed(6)}</td></tr>
            )) : <tr><td colSpan={5} className="empty">Sin consumo</td></tr>}</tbody></table>
        )}
      </div>

      <div className="card-head" style={{ alignItems: "center", marginBottom: 8 }}>
        <h3 className="sec-title" style={{ margin: 0 }}>Últimas llamadas</h3>
        {pages > 1 && (
          <div className="pager">
            <button className="ibtn" onClick={() => setPage(p => Math.max(0, p - 1))} disabled={page === 0} aria-label="Anterior"><Icon name="arrowleft" size={16} /></button>
            <span className="muted" style={{ fontSize: 12.5 }}>{page + 1} / {pages}</span>
            <button className="ibtn" onClick={() => setPage(p => Math.min(pages - 1, p + 1))} disabled={page >= pages - 1} aria-label="Siguiente" style={{ transform: "rotate(180deg)" }}><Icon name="arrowleft" size={16} /></button>
          </div>
        )}
      </div>
      <table><thead><tr><th>Fecha (UTC)</th><th>Conversación</th><th>Modelo</th><th className="num">In</th><th className="num">Out</th><th className="num">US$</th></tr></thead>
        <tbody>{slice.length ? slice.map((e, i) => (
          <tr key={i}><td className="mono" style={{ fontSize: 11.5 }}>{(e.created_at || "").replace("T", " ").slice(0, 19)}</td><td className="mono" style={{ fontSize: 11.5 }}>{e.conversation_id || "—"}</td><td>{e.model}</td><td className="num">{fmtInt(e.tokens_in)}</td><td className="num">{fmtInt(e.tokens_out)}</td><td className="num">{Number(e.cost_usd).toFixed(6)}</td></tr>
        )) : <tr><td colSpan={6} className="empty">Sin eventos</td></tr>}</tbody></table>
    </>
  );
}

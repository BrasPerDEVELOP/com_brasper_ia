"use client";
import { useEffect, useState } from "react";
import { api, UsageRow } from "@/lib/api";

interface Ev { created_at: string; tenant_id: string; conversation_id: string; model: string; tokens_in: number; tokens_out: number; cost_usd: number; }

export default function Consumo() {
  const [summary, setSummary] = useState<UsageRow[]>([]);
  const [events, setEvents] = useState<Ev[]>([]);
  const [err, setErr] = useState("");
  useEffect(() => {
    api<{ summary: UsageRow[]; events: Ev[] }>("/api/usage").then(d => { setSummary(d.summary); setEvents(d.events); }).catch(e => setErr((e as Error).message));
  }, []);
  if (err) return <div className="empty">⚠️ {err}</div>;
  return (
    <>
      <div className="usage-note">Economía unitaria real: cada llamada al LLM registra tenant, tokens y costo. Así sabes si un cliente te come el margen antes de que sea tarde.</div>
      <h3 className="sec-title">Resumen por cliente</h3>
      <table><thead><tr><th>Tenant</th><th className="num">Llamadas</th><th className="num">Tokens in</th><th className="num">Tokens out</th><th className="num">Costo (US$)</th></tr></thead>
        <tbody>{summary.length ? summary.map(s => (
          <tr key={s.tenant_id}><td>{s.tenant_id}</td><td className="num">{s.calls}</td><td className="num">{(s.tokens_in || 0).toLocaleString("es")}</td><td className="num">{(s.tokens_out || 0).toLocaleString("es")}</td><td className="num">{Number(s.cost_usd || 0).toFixed(6)}</td></tr>
        )) : <tr><td colSpan={5} className="empty">Sin consumo registrado aún</td></tr>}</tbody></table>
      <h3 className="sec-title">Últimos eventos</h3>
      <table><thead><tr><th>Fecha (UTC)</th><th>Tenant</th><th>Conversación</th><th>Modelo</th><th className="num">In</th><th className="num">Out</th><th className="num">US$</th></tr></thead>
        <tbody>{events.length ? events.map((e, i) => (
          <tr key={i}><td className="mono" style={{ fontSize: 11 }}>{(e.created_at || "").replace("T", " ").slice(0, 19)}</td><td>{e.tenant_id}</td><td className="mono" style={{ fontSize: 11 }}>{e.conversation_id || "—"}</td><td>{e.model}</td><td className="num">{e.tokens_in}</td><td className="num">{e.tokens_out}</td><td className="num">{Number(e.cost_usd).toFixed(6)}</td></tr>
        )) : <tr><td colSpan={7} className="empty">Sin eventos</td></tr>}</tbody></table>
    </>
  );
}

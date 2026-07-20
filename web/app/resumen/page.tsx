"use client";
import { useEffect, useState } from "react";
import { api, money, Tenant, UsageRow } from "@/lib/api";
import Icon from "@/components/Icon";

const PEND = [
  "Constructor de flujos visual (React Flow)",
  "Analítica / embudo con datos históricos",
  "Base de conocimiento (RAG)",
  "Asistente de conexión de WhatsApp (Meta Embedded Signup)",
];

export default function Resumen() {
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [usage, setUsage] = useState<UsageRow[]>([]);
  const [backend, setBackend] = useState("");
  const [err, setErr] = useState("");
  useEffect(() => {
    Promise.all([
      api<{ tenants: Tenant[] }>("/api/tenants"),
      api<{ summary: UsageRow[] }>("/api/usage"),
    ]).then(([t, u]) => { setTenants(t.tenants); setUsage(u.summary); })
      .catch(e => setErr((e as Error).message));
    // Backend real (Postgres/SQLite) desde /health; no debe romper la página.
    api<{ db: { backend: string } }>("/health")
      .then(h => setBackend(h.db?.backend || "")).catch(() => { });
  }, []);
  const dbLabel = backend === "postgres" ? "PostgreSQL" : backend === "sqlite" ? "SQLite" : "la base de datos";

  if (err) return <div className="empty">⚠️ {err}</div>;
  const ingreso = tenants.reduce((a, t) => a + (t.fee_usd || 0), 0);
  const costo = tenants.reduce((a, t) => a + (t.cost_usd || 0), 0);
  const margen = ingreso - costo;
  const llamadas = usage.reduce((a, s) => a + (s.calls || 0), 0);

  const stat = (icon: string, tint: string, num: React.ReactNode, lbl: string, cls = "") => (
    <div className="stat">
      <div className="stat-top"><div className={`ic ic-${tint}`}><Icon name={icon} /></div></div>
      <div className={`num ${cls}`}>{num}</div><div className="lbl">{lbl}</div>
    </div>
  );

  return (
    <>
      <div className="usage-note">Operación con datos <b>reales</b>: config de tenants + consumo medido en {dbLabel}. {llamadas} llamadas al LLM registradas.</div>
      <div className="stats">
        {stat("building", "blue", tenants.length, "Clientes gestionados")}
        {stat("dollar", "green", money(ingreso), "Ingreso mensual (fee)")}
        {stat("ai", "amber", money(costo), "Costo IA real medido", "bad")}
        {stat("chart", "green", <>{money(margen)} <span className="muted" style={{ fontSize: 13 }}>({ingreso ? Math.round(margen / ingreso * 100) : 0}%)</span></>, "Margen", "ok")}
      </div>
      <h3 className="sec-title">Por cliente</h3>
      <table><thead><tr><th>Cliente</th><th>Rubro</th><th className="num">Llamadas</th><th className="num">Costo IA</th><th className="num">Fee</th><th className="num">Margen</th></tr></thead>
        <tbody>{tenants.map(t => (
          <tr key={t.id}><td>{t.name}</td><td className="muted">{t.vertical}</td><td className="num">{t.calls}</td>
            <td className="num bad">{money(t.cost_usd)}</td><td className="num">{money(t.fee_usd)}</td><td className="num ok">{money(t.margin_usd)}</td></tr>
        ))}</tbody></table>
      <h3 className="sec-title">En construcción · próxima fase</h3>
      <div className="card">
        <p className="muted" style={{ margin: "0 0 8px", fontSize: 13 }}>Estas pantallas existen en la maqueta de venta pero <b>todavía no tienen backend real</b>, por eso no están en el panel (no las falseamos):</p>
        <ul style={{ margin: 0, paddingLeft: 18, color: "var(--muted)", fontSize: 13, lineHeight: 1.9 }}>
          {PEND.map(p => <li key={p}>{p}</li>)}
        </ul>
      </div>
    </>
  );
}

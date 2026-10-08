"use client";
import { useCallback, useEffect, useState } from "react";
import { api, OpsAlert, OpsMetrics } from "@/lib/api";
import Icon from "@/components/Icon";

interface DeadJob { id?: string; type?: string; job_type?: string; error?: string; attempts?: number; payload?: Record<string, unknown>; failed_at?: string }

const VITAL_LABEL: Record<string, string> = { LCP: "LCP · carga (ms)", INP: "INP · respuesta (ms)", CLS: "CLS · estabilidad", FCP: "FCP (ms)", TTFB: "TTFB (ms)", FID: "FID (ms)" };
const VITAL_GOOD: Record<string, number> = { LCP: 2500, INP: 200, CLS: 0.1, FCP: 1800, TTFB: 800, FID: 100 };

export default function Ops() {
  const [alerts, setAlerts] = useState<OpsAlert[] | null>(null);
  const [metrics, setMetrics] = useState<OpsMetrics | null>(null);
  const [dead, setDead] = useState<{ count: number; jobs: DeadJob[] } | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState("");
  const [at, setAt] = useState<Date | null>(null);

  const load = useCallback(() => {
    Promise.all([
      api<{ alerts: OpsAlert[] }>("/api/ops/alerts").then(d => setAlerts(d.alerts)),
      api<OpsMetrics>("/api/ops/metrics").then(setMetrics),
      api<{ count: number; jobs: DeadJob[] }>("/api/ops/dead-letter?limit=50").then(setDead),
      api<Record<string, unknown>>("/health").then(setHealth).catch(() => setHealth(null)),
    ]).then(() => { setErr(""); setAt(new Date()); }).catch(e => setErr((e as Error).message));
  }, []);

  useEffect(() => { load(); const t = setInterval(load, 30000); return () => clearInterval(t); }, [load]);

  if (err) return <div className="usage-note err"><Icon name="alert" size={16} /> {err}</div>;
  const db = health?.db as { backend?: string; ok?: boolean } | undefined;
  const redis = health?.redis as { configured?: boolean; ok?: boolean } | undefined;
  const convCount = metrics?.conversations.by_tenant?.[0]?.count ?? 0;
  const msgCount = metrics?.messages?.by_tenant?.[0]?.count ?? 0;
  const vitals = Object.entries(metrics?.web_vitals || {});

  return (
    <>
      <div className="row" style={{ marginBottom: 12 }}>
        <span className="muted" style={{ fontSize: 12.5 }}>Se actualiza cada 30 s{at ? ` · última ${at.toLocaleTimeString("es")}` : ""}.</span>
        <span className="grow" />
        <button className="btn btn-ghost btn-sm" onClick={load}><Icon name="refresh" size={14} /> Actualizar</button>
      </div>

      <div className="stats">
        <div className="stat">
          <div className={"ic " + (health?.ok ? "ic-green" : "ic-coral")}><Icon name={health?.ok ? "check" : "alert"} /></div>
          <div className="num" style={{ fontSize: 22 }}>{health ? (health.ok ? "Operativo" : "Con fallas") : "—"}</div>
          <div className="lbl">API · entorno {String(health?.env || "—")}</div>
        </div>
        <div className="stat">
          <div className={"ic " + (db?.ok ? "ic-green" : "ic-coral")}><Icon name="file" /></div>
          <div className="num" style={{ fontSize: 22 }}>{db?.backend || "—"}</div>
          <div className="lbl">Base de datos {db?.ok ? "responde" : "sin respuesta"}</div>
        </div>
        <div className="stat">
          <div className={"ic " + (redis?.configured ? (redis.ok ? "ic-green" : "ic-coral") : "ic-amber")}><Icon name="zap" /></div>
          <div className="num" style={{ fontSize: 22 }}>{redis?.configured ? (redis.ok ? "OK" : "Caído") : "No config."}</div>
          <div className="lbl">Redis (lock por conversación, jobs)</div>
        </div>
        <div className="stat">
          <div className={"ic " + ((dead?.count || 0) > 0 ? "ic-amber" : "ic-blue")}><Icon name="inbox" /></div>
          <div className="num">{dead?.count ?? 0}</div>
          <div className="lbl">Jobs en dead-letter · {convCount} conversaciones · {msgCount} mensajes</div>
        </div>
      </div>

      <div className="cards" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
        <div className="card">
          <h3>Alertas</h3>
          {alerts === null ? <div className="muted">Cargando…</div> : alerts.length ? alerts.map((a, i) => (
            <div key={i} className={"alert-row " + a.level}>
              <Icon name={a.level === "critical" ? "alert" : "info"} size={16} />
              <div>
                <b>{a.message}</b>
                <div className="muted" style={{ fontSize: 12 }}>
                  <span className="mono">{a.code}</span>
                  {a.count !== undefined && ` · ${a.count}`}
                  {a.cost_usd !== undefined && ` · US$ ${a.cost_usd} de ${a.threshold_usd}`}
                </div>
              </div>
            </div>
          )) : <div className="ok" style={{ display: "flex", gap: 6, alignItems: "center" }}><Icon name="check" size={16} /> Sin alertas activas.</div>}
        </div>

        <div className="card">
          <h3>Velocidad del panel (Core Web Vitals)</h3>
          <p className="muted" style={{ fontSize: 12.5, margin: "0 0 8px" }}>p75 reportado por los navegadores del equipo en esta sesión del servidor.</p>
          {vitals.length ? (
            <table><thead><tr><th>Métrica</th><th className="num">p75</th><th className="num">Muestras</th><th>Estado</th></tr></thead>
              <tbody>{vitals.map(([k, v]) => {
                const good = v.p75 !== null && v.p75 <= (VITAL_GOOD[k] ?? Infinity);
                return (
                  <tr key={k}><td>{VITAL_LABEL[k] || k}</td><td className="num">{v.p75 ?? "—"}</td><td className="num">{v.samples}</td>
                    <td><span className={"tag " + (good ? "ok" : "warn")}>{good ? "bien" : "mejorar"}</span></td></tr>
                );
              })}</tbody></table>
          ) : <div className="muted" style={{ fontSize: 13 }}>Aún sin muestras. Navega el panel un rato y vuelve.</div>}
        </div>
      </div>

      <h3 className="sec-title">Dead-letter (jobs agotados)</h3>
      <table><thead><tr><th>Tipo</th><th>Error</th><th className="num">Intentos</th><th>Payload</th></tr></thead>
        <tbody>{dead?.jobs?.length ? dead.jobs.map((j, i) => (
          <tr key={j.id || i}><td className="mono">{j.type || j.job_type || "—"}</td><td style={{ fontSize: 12.5 }}>{j.error || "—"}</td><td className="num">{j.attempts ?? "—"}</td>
            <td><code className="mono" style={{ fontSize: 11 }}>{JSON.stringify(j.payload || {}).slice(0, 120)}</code></td></tr>
        )) : <tr><td colSpan={4} className="empty">Sin jobs fallidos{redis?.configured ? "" : " (sin Redis no hay cola)"}.</td></tr>}</tbody></table>
    </>
  );
}

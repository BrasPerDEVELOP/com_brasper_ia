"use client";
import { useEffect, useState } from "react";
import { api, can, KnowledgeEntry, ToolContract, WaConnection } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import Icon from "@/components/Icon";

interface KnowledgeResp { version: string | null; path: string; approved: number; draft: number; entries: KnowledgeEntry[] }
interface ToolsResp { tools: ToolContract[]; features: Record<string, boolean> }

const FLAG_LABEL: Record<string, string> = {
  knowledge: "FAQ con fuente (sin LLM)", status_intent: "Estado de envío → asesor con resumen", anti_loop: "Límite de repeticiones",
  audio_confirmation: "Confirmar cifras ambiguas en audios", webhook_dedup: "Deduplicar webhooks", presence_required: "Asignar solo a asesores presentes",
  coex: "Coexistencia con la app WhatsApp Business",
};

export default function Conocimiento() {
  const me = useMe();
  const [kb, setKb] = useState<KnowledgeResp | null>(null);
  const [tools, setTools] = useState<ToolsResp | null>(null);
  const [conns, setConns] = useState<{ connections: WaConnection[]; coex_enabled: boolean } | null>(null);
  const [filter, setFilter] = useState<"all" | "approved" | "draft">("all");

  useEffect(() => {
    api<KnowledgeResp>("/api/knowledge").then(setKb).catch(() => {});
    if (can(me, "usage:read")) api<ToolsResp>("/api/tools").then(setTools).catch(() => {});
    if (can(me, "config:read")) api<{ connections: WaConnection[]; coex_enabled: boolean }>("/api/whatsapp/connections").then(setConns).catch(() => {});
  }, [me]);

  const entries = (kb?.entries || []).filter(e => filter === "all" || (filter === "approved" ? e.status === "approved" : e.status !== "approved"));

  return (
    <>
      <div className="usage-note">
        El bot responde preguntas informativas <b>solo</b> con entradas aprobadas de la FAQ, citando la fuente y la fecha de revisión. Las entradas en borrador no se sirven: el bot dice que no tiene la información confirmada. La edición se hace en el repositorio (<code className="mono">{kb?.path || "backend/data/knowledge/brasper/faq.json"}</code>) vía PR.
      </div>

      <div className="stats">
        <div className="stat"><div className="ic ic-green"><Icon name="check" /></div><div className="num">{kb?.approved ?? "—"}</div><div className="lbl">Entradas aprobadas (ES/PT)</div></div>
        <div className="stat"><div className="ic ic-amber"><Icon name="note" /></div><div className="num">{kb?.draft ?? "—"}</div><div className="lbl">Borradores pendientes del equipo comercial</div></div>
        <div className="stat"><div className="ic ic-blue"><Icon name="zap" /></div><div className="num">{tools ? tools.tools.filter(t => t.available).length : "—"}</div><div className="lbl">Herramientas disponibles · {tools ? tools.tools.filter(t => !t.available).length : "—"} sin API</div></div>
        <div className="stat"><div className="ic ic-coral"><Icon name="whatsapp" /></div><div className="num">{conns ? conns.connections.length : "—"}</div><div className="lbl">Conexiones WhatsApp · Coex {conns?.coex_enabled ? "activa" : "inactiva"}</div></div>
      </div>

      <div className="card-head" style={{ alignItems: "center" }}>
        <h3 className="sec-title" style={{ margin: 0 }}>Base de conocimiento {kb?.version ? <span className="tag">v{kb.version}</span> : null}</h3>
        <div className="seg" role="tablist">
          {(["all", "approved", "draft"] as const).map(f => (
            <button key={f} role="tab" aria-selected={filter === f} className={filter === f ? "on" : ""} onClick={() => setFilter(f)}>
              {f === "all" ? "Todas" : f === "approved" ? "Aprobadas" : "Borradores"}
            </button>
          ))}
        </div>
      </div>
      <table><thead><tr><th>Pregunta</th><th>Idioma</th><th>Estado</th><th>Fuente</th><th>Revisión</th></tr></thead>
        <tbody>{entries.length ? entries.map(e => (
          <tr key={e.id}><td>{e.question}</td><td><span className="tag">{e.lang.toUpperCase()}</span></td>
            <td><span className={"tag " + (e.status === "approved" ? "ok" : "warn")}>{e.status === "approved" ? "aprobada" : "borrador"}</span></td>
            <td className="mono" style={{ fontSize: 11 }}>{e.source}</td><td className="mono" style={{ fontSize: 11.5 }}>{e.reviewed_at || "—"}</td></tr>
        )) : <tr><td colSpan={5} className="empty">Sin entradas</td></tr>}</tbody></table>

      {tools && (
        <>
          <h3 className="sec-title">Contratos de herramientas</h3>
          <p className="muted" style={{ fontSize: 12.5, marginTop: -6 }}>Cada herramienta declara entradas permitidas, permiso, timeout y si escribe. “Sin API” significa que la capacidad no existe en la API IA de Brasper: el bot deriva a un asesor en vez de inventar.</p>
          <table><thead><tr><th>Herramienta</th><th>Descripción</th><th>Entradas</th><th className="num">Timeout</th><th>Escribe</th><th>Estado</th></tr></thead>
            <tbody>{tools.tools.map(t => (
              <tr key={t.name}><td className="mono">{t.name}</td><td style={{ fontSize: 12.5 }}>{t.description}</td>
                <td className="mono" style={{ fontSize: 11 }}>{Object.entries(t.inputs).map(([k, v]) => `${k}${t.required.includes(k) ? "*" : ""}: ${v}`).join(", ")}</td>
                <td className="num">{t.timeout_s}s</td><td>{t.write ? <span className="tag warn">sí</span> : <span className="tag">no</span>}</td>
                <td>{t.available ? <span className="tag ok">disponible</span> : <span className="tag danger">sin API</span>}</td></tr>
            ))}</tbody></table>

          <h3 className="sec-title">Flags de despliegue gradual</h3>
          <p className="muted" style={{ fontSize: 12.5, marginTop: -6 }}>Se configuran en <code className="mono">tenants.json → features</code> (Admin API con deep-merge). Permiten activar o revertir cada capacidad sin redesplegar.</p>
          <div className="cards" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))" }}>
            {Object.entries(tools.features).map(([k, v]) => (
              <div key={k} className="card" style={{ padding: "12px 14px" }}>
                <div className="card-head" style={{ marginBottom: 2 }}><b style={{ fontSize: 13.5 }}>{FLAG_LABEL[k] || k}</b><span className={"tag " + (v ? "ok" : "closed")}>{v ? "ON" : "OFF"}</span></div>
                <code className="mono muted" style={{ fontSize: 11 }}>features.{k}</code>
              </div>
            ))}
          </div>
        </>
      )}

      {conns && (
        <>
          <h3 className="sec-title">Conexiones WhatsApp</h3>
          <table><thead><tr><th>ID</th><th>Etiqueta</th><th>Modalidad</th><th>phone_number_id</th><th>Número</th><th>Estado</th></tr></thead>
            <tbody>{conns.connections.length ? conns.connections.map(c => (
              <tr key={c.id}><td className="mono">{c.id}</td><td>{c.label}</td>
                <td><span className={"tag " + (c.mode === "coex" ? "coex" : "info")}>{c.mode === "coex" ? "Coexistencia" : "API estándar"}</span></td>
                <td className="mono" style={{ fontSize: 11.5 }}>{c.phone_number_id || "—"}</td><td>{c.display_phone || "—"}</td>
                <td>{c.configured ? <span className="tag ok">configurada</span> : <span className="tag warn">sin credenciales</span>}</td></tr>
            )) : <tr><td colSpan={6} className="empty">Sin conexiones configuradas.</td></tr>}</tbody></table>
        </>
      )}
    </>
  );
}

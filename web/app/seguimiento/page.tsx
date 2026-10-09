"use client";
import { useEffect, useState } from "react";
import { api, can } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import { useToast } from "@/components/Toast";

type Settings = { enabled: boolean; surveys: boolean; timezone: string; weekdays: number[];
  start_hour: number; end_hour: number; waiting_minutes: number; inactivity_minutes: number;
  max_reminders: number; sla_minutes: number; expiry_hours: number; allowed_channels: string[];
  whatsapp_window_seconds: number | null; policy_source: string };
type Response = { version: number; settings: Settings; metrics?: { satisfaction: { responses: number; average: number | null }; jobs: { state: string; count: number }[] } };

export default function Seguimiento() {
  const me = useMe(); const { toast } = useToast();
  const [data, setData] = useState<Response | null>(null);
  const [draft, setDraft] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  function load() { api<Response>("/api/admin/engagement").then(d => { setData(d); setDraft(d.settings); setError(""); }).catch(e => setError(e.message)); }
  useEffect(() => { load(); }, []);
  const editable = can(me, "tenants:write");
  async function save() {
    if (!draft || !data) return;
    setBusy(true);
    try { await api("/api/admin/engagement", { method: "PUT", body: JSON.stringify({ settings: draft, expected_version: data.version }) }); toast("Configuración guardada", "ok"); load(); }
    catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  }
  if (error) return <div role="alert">{error} <button className="btn" onClick={load}>Reintentar</button></div>;
  if (!draft || !data) return <p>Cargando configuración…</p>;
  const numeric = [
    ["start_hour", "Hora de apertura (0–23)", 0, 23], ["end_hour", "Hora de cierre (1–24)", 1, 24],
    ["waiting_minutes", "Aviso de espera cada (minutos)", 1, 10080], ["inactivity_minutes", "Recordatorio de inactividad cada (minutos)", 1, 10080],
    ["max_reminders", "Máximo de recordatorios por conversación sin respuesta", 0, 3], ["sla_minutes", "Umbral de alerta de espera (minutos)", 1, 10080],
    ["expiry_hours", "Vencimiento de recordatorios (horas)", 1, 168],
  ] as const;
  return <>
    <h2>Encuestas y seguimiento</h2>
    <p>Los recordatorios requieren consentimiento del cliente, horario de atención y un canal habilitado. Cerrar el chat no completa una operación financiera.</p>
    <p className="usage-note">Para aceptar recordatorios, el cliente puede escribir «acepto recordatorios» o «aceito lembretes». Puede retirarlo con «no quiero recordatorios» o «não quero lembretes». Una encuesta es opcional y no se repite para el mismo cierre.</p>
    <fieldset disabled={!editable || busy} className="card">
      <legend>Configuración · versión {data.version}</legend>
      <label><input type="checkbox" checked={draft.enabled} onChange={e => setDraft({ ...draft, enabled: e.target.checked })} /> Habilitar seguimiento</label><br />
      <label><input type="checkbox" checked={draft.surveys} onChange={e => setDraft({ ...draft, surveys: e.target.checked })} /> Ofrecer encuesta después del cierre</label>
      <label className="fld">Zona horaria IANA<input value={draft.timezone} onChange={e => setDraft({ ...draft, timezone: e.target.value })} placeholder="America/Lima" /></label>
      <div>Días de atención</div>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>{["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"].map((label, day) => <label key={day}><input type="checkbox" checked={draft.weekdays.includes(day)} onChange={e => setDraft({ ...draft, weekdays: e.target.checked ? [...draft.weekdays, day] : draft.weekdays.filter(d => d !== day) })} /> {label}</label>)}</div>
      <div className="cards">{numeric.map(([key, label, min, max]) => <label className="fld" key={key}>{label}<input type="number" min={min} max={max} value={draft[key]} onChange={e => setDraft({ ...draft, [key]: Number(e.target.value) })} /></label>)}</div>
      <div>Canales habilitados</div>
      {["webchat", "telegram", "whatsapp"].map(channel => <label key={channel} style={{ marginRight: 16 }}><input type="checkbox" checked={draft.allowed_channels.includes(channel)} onChange={e => setDraft({ ...draft, allowed_channels: e.target.checked ? [...draft.allowed_channels, channel] : draft.allowed_channels.filter(c => c !== channel) })} /> {channel}</label>)}
      <label className="fld">Ventana WhatsApp verificada (segundos, máximo 86400)<input type="number" min={1} max={86400} value={draft.whatsapp_window_seconds ?? ""} onChange={e => setDraft({ ...draft, whatsapp_window_seconds: e.target.value ? Number(e.target.value) : null })} /></label>
      <label className="fld">Fuente y fecha de verificación de la política de WhatsApp<input maxLength={500} value={draft.policy_source} onChange={e => setDraft({ ...draft, policy_source: e.target.value })} /></label>
      <p>Fuera de esa ventana se suprime el recordatorio; no se sustituye por una plantilla sin aprobación. Los envíos cuyo resultado sea incierto requieren revisión y no se reintentan automáticamente.</p>
      <button className="btn" onClick={save} disabled={JSON.stringify(draft) === JSON.stringify(data.settings)}>{busy ? "Guardando…" : "Guardar configuración"}</button>
    </fieldset>
    <div className="card"><h3>Resultados</h3><p>Respuestas: {data.metrics?.satisfaction.responses ?? 0} · Promedio: {data.metrics?.satisfaction.average?.toFixed(2) ?? "Sin respuestas"}</p>
      <table><thead><tr><th>Estado del seguimiento</th><th>Cantidad</th></tr></thead><tbody>{data.metrics?.jobs.map(j => <tr key={j.state}><td>{j.state}</td><td>{j.count}</td></tr>)}</tbody></table>
    </div>
  </>;
}

"use client";
import { useEffect, useState } from "react";
import { api, can } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import { useToast } from "@/components/Toast";

type Scope = { channels: string[]; connections: string[]; sectors: string[] };
type PanelUser = { id: number; email: string; name: string; role: string; access_scope: Scope };
type Conflict = { id: string; provider: string; connection_id: string; external_id: string;
  existing_contact_id: string; proposed_contact_id: string; reason: string; created_at: string };

const CHANNELS = ["whatsapp", "telegram", "webchat"];
const list = (raw: string) => raw.split(",").map(v => v.trim()).filter(Boolean);

function ScopeRow({ user, editable, onSaved }: { user: PanelUser; editable: boolean; onSaved: () => void }) {
  const { toast } = useToast();
  const [channels, setChannels] = useState(user.access_scope.channels);
  const [connections, setConnections] = useState(user.access_scope.connections.join(", "));
  const [sectors, setSectors] = useState(user.access_scope.sectors.join(", "));
  const [busy, setBusy] = useState(false);
  const draft: Scope = { channels: [...channels].sort(), connections: list(connections), sectors: list(sectors).map(s => s.toLowerCase()) };
  const dirty = JSON.stringify(draft) !== JSON.stringify(user.access_scope);
  async function save() {
    setBusy(true);
    try {
      await api(`/api/admin/users/${encodeURIComponent(user.email)}/scope`, { method: "PUT", body: JSON.stringify(draft) });
      toast("Alcance guardado", "ok"); onSaved();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  }
  const owner = user.role === "owner";
  return <tr>
    <td>{user.name}<br /><small>{user.email}</small></td>
    <td>{user.role}</td>
    <td>{owner ? <small>Acceso total</small> : CHANNELS.map(c => <label key={c} style={{ marginRight: 10 }}>
      <input type="checkbox" disabled={!editable || busy} checked={channels.includes(c)}
        onChange={e => setChannels(e.target.checked ? [...channels, c] : channels.filter(x => x !== c))} /> {c}</label>)}</td>
    <td>{owner ? "—" : <input aria-label={`Números de ${user.email}`} disabled={!editable || busy} value={connections}
      onChange={e => setConnections(e.target.value)} placeholder="todas" />}</td>
    <td>{owner ? "—" : <input aria-label={`Sectores de ${user.email}`} disabled={!editable || busy} value={sectors}
      onChange={e => setSectors(e.target.value)} placeholder="todos" />}</td>
    <td>{!owner && editable && <button className="btn" disabled={!dirty || busy} onClick={save}>{busy ? "Guardando…" : "Guardar"}</button>}</td>
  </tr>;
}

export default function Accesos() {
  const me = useMe(); const { toast } = useToast();
  const [users, setUsers] = useState<PanelUser[] | null>(null);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [error, setError] = useState("");
  function load() {
    api<{ users: PanelUser[] }>("/api/admin/users").then(d => { setUsers(d.users); setError(""); }).catch(e => setError(e.message));
    if (can(me, "config:read")) api<{ conflicts: Conflict[] }>("/api/admin/contact-conflicts").then(d => setConflicts(d.conflicts)).catch(() => setConflicts([]));
  }
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  async function review(id: string) {
    try { await api(`/api/admin/contact-conflicts/${id}/resolve`, { method: "POST" }); toast("Conflicto marcado como revisado", "ok"); load(); }
    catch (e) { toast((e as Error).message, "err"); }
  }
  if (error) return <div role="alert">{error} <button className="btn" onClick={load}>Reintentar</button></div>;
  if (!users) return <p>Cargando usuarios…</p>;
  const editable = can(me, "users:write");
  return <>
    <h2>Accesos</h2>
    <p>Limita qué conversaciones ve y atiende cada persona. Un campo vacío no restringe. Los sectores son etiquetas <code>sector:nombre</code> de la conversación. La restricción se aplica en el servidor: bandeja, detalle, adjuntos, respuestas y asignación automática.</p>
    <div className="card" style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>Usuario</th><th>Rol</th><th>Canales</th><th>Números (IDs de conexión)</th><th>Sectores</th><th /></tr></thead>
        <tbody>{users.map(u => <ScopeRow key={`${u.email}:${JSON.stringify(u.access_scope)}`} user={u} editable={editable} onSaved={load} />)}</tbody>
      </table>
      {!editable && <p className="usage-note">Solo quien gestiona usuarios puede cambiar el alcance.</p>}
    </div>
    {can(me, "config:read") && <div className="card">
      <h3>Contactos por revisar</h3>
      <p>Un identificador del canal coincide con otro contacto. No se fusionan automáticamente: revisa el historial antes de unirlos.</p>
      {conflicts.length === 0 ? <p>No hay conflictos abiertos.</p> :
        <table><thead><tr><th>Canal</th><th>Identificador</th><th>Contacto actual</th><th>Contacto sugerido</th><th>Fecha</th><th /></tr></thead>
          <tbody>{conflicts.map(c => <tr key={c.id}>
            <td>{c.provider}{c.connection_id ? ` · ${c.connection_id}` : ""}</td><td><code>{c.external_id}</code></td>
            <td><code>{c.existing_contact_id.slice(0, 8)}</code></td><td><code>{c.proposed_contact_id.slice(0, 8)}</code></td>
            <td>{new Date(c.created_at).toLocaleString()}</td>
            <td>{can(me, "config:write") && <button className="btn" onClick={() => review(c.id)}>Marcar revisado</button>}</td>
          </tr>)}</tbody></table>}
    </div>}
  </>;
}

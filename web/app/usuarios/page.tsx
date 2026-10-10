"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import { useToast } from "@/components/Toast";

type Scope = { channels: string[]; connections: string[]; sectors: string[] };
type PanelUser = { id: number; email: string; name: string; role: string; access_scope: Scope; active: boolean;
  has_password: boolean; must_change_password: boolean; active_sessions: number };
type Draft = { email: string; name: string; role: string; channels: string[]; connections: string; sectors: string; password: string };

const CHANNELS = ["whatsapp", "telegram", "webchat"];
const ROLE_HELP: Record<string, string> = {
  owner: "acceso total y gestión de usuarios", admin: "opera y configura; ve usuarios", builder: "configura bot y prompts",
  analyst: "solo lectura y consumo", agent: "atiende conversaciones", billing: "facturación y consumo", viewer: "solo lectura",
};
const list = (raw: string) => raw.split(",").map(v => v.trim()).filter(Boolean);
const empty = (role = "agent"): Draft => ({ email: "", name: "", role, channels: [], connections: "", sectors: "", password: "" });
const fromUser = (u: PanelUser): Draft => ({ email: u.email, name: u.name, role: u.role, channels: u.access_scope.channels,
  connections: u.access_scope.connections.join(", "), sectors: u.access_scope.sectors.join(", "), password: "" });
const scopeOf = (d: Draft): Scope => ({ channels: [...d.channels].sort(), connections: list(d.connections), sectors: list(d.sectors).map(s => s.toLowerCase()) });

function UserForm({ draft, roles, editing, busy, onChange, onSubmit, onCancel }: {
  draft: Draft; roles: string[]; editing: boolean; busy: boolean;
  onChange: (d: Draft) => void; onSubmit: () => void; onCancel: () => void;
}) {
  const owner = draft.role === "owner";
  return (
    <form className="card" onSubmit={e => { e.preventDefault(); onSubmit(); }} style={{ display: "grid", gap: 10 }}>
      <h3>{editing ? `Editar ${draft.email}` : "Nuevo usuario"}</h3>
      <div className="cards">
        <label className="fld">Nombre<input required maxLength={80} value={draft.name} onChange={e => onChange({ ...draft, name: e.target.value })} /></label>
        <label className="fld">Correo<input required type="email" maxLength={254} disabled={editing} value={draft.email}
          onChange={e => onChange({ ...draft, email: e.target.value })} /></label>
        <label className="fld">Rol
          <select value={draft.role} onChange={e => onChange({ ...draft, role: e.target.value })}>
            {roles.map(r => <option key={r} value={r}>{r} — {ROLE_HELP[r] || r}</option>)}
          </select>
        </label>
        {!editing && <label className="fld">Contraseña temporal (opcional)
          <input type="password" autoComplete="new-password" minLength={10} maxLength={256} value={draft.password}
            placeholder="vacío = se genera una" onChange={e => onChange({ ...draft, password: e.target.value })} /></label>}
      </div>
      {owner ? <p className="usage-note">El owner tiene acceso total: el alcance no aplica.</p> : <>
        <div>Canales (ninguno marcado = todos)</div>
        <div>{CHANNELS.map(c => <label key={c} style={{ marginRight: 14 }}>
          <input type="checkbox" checked={draft.channels.includes(c)}
            onChange={e => onChange({ ...draft, channels: e.target.checked ? [...draft.channels, c] : draft.channels.filter(x => x !== c) })} /> {c}</label>)}</div>
        <div className="cards">
          <label className="fld">Números (IDs de conexión, separados por coma)<input value={draft.connections} placeholder="todos"
            onChange={e => onChange({ ...draft, connections: e.target.value })} /></label>
          <label className="fld">Sectores (separados por coma)<input value={draft.sectors} placeholder="todos"
            onChange={e => onChange({ ...draft, sectors: e.target.value })} /></label>
        </div>
      </>}
      <div style={{ display: "flex", gap: 8 }}>
        <button className="btn" type="submit" disabled={busy || !draft.name.trim() || !draft.email.trim()}>
          {busy ? "Guardando…" : editing ? "Guardar cambios" : "Crear usuario"}</button>
        <button className="btn btn-ghost" type="button" onClick={onCancel} disabled={busy}>Cancelar</button>
      </div>
    </form>
  );
}

export default function Usuarios() {
  const me = useMe(); const { toast } = useToast();
  const [users, setUsers] = useState<PanelUser[] | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState<Draft | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState<{ email: string; password: string } | null>(null);
  const isOwner = me?.role === "owner";

  function load() {
    api<{ users: PanelUser[]; roles: string[] }>("/api/admin/users")
      .then(d => { setUsers(d.users); setRoles(d.roles || []); setError(""); })
      .catch(e => setError(e.message));
  }
  useEffect(() => { load(); }, []);

  async function run(label: string, fn: () => Promise<unknown>) {
    setBusy(true);
    try { await fn(); toast(label, "ok"); load(); return true; }
    catch (e) { toast((e as Error).message, "err"); return false; }
    finally { setBusy(false); }
  }
  const path = (email: string, action = "") => `/api/admin/users/${encodeURIComponent(email)}${action}`;

  async function submit() {
    if (!draft) return;
    const scope = scopeOf(draft);
    if (editing) {
      const ok = await run("Usuario actualizado", () => api(path(draft.email), { method: "PATCH",
        body: JSON.stringify({ name: draft.name, role: draft.role, access_scope: scope }) }));
      if (ok) setDraft(null);
      return;
    }
    setBusy(true);
    try {
      const d = await api<{ temporary_password: string | null }>("/api/admin/users", { method: "POST", body: JSON.stringify({
        email: draft.email.trim(), name: draft.name.trim(), role: draft.role, access_scope: scope, password: draft.password || undefined }) });
      if (d.temporary_password) setSecret({ email: draft.email.trim().toLowerCase(), password: d.temporary_password });
      toast("Usuario creado. Deberá cambiar la contraseña al entrar.", "ok");
      setDraft(null); load();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  }

  async function resetPassword(u: PanelUser) {
    if (!window.confirm(`¿Generar una contraseña temporal para ${u.email}? Se cerrarán todas sus sesiones.`)) return;
    setBusy(true);
    try {
      const d = await api<{ temporary_password: string | null }>(path(u.email, "/password-reset"), { method: "POST", body: "{}" });
      if (d.temporary_password) setSecret({ email: u.email, password: d.temporary_password });
      toast("Contraseña temporal generada", "ok"); load();
    } catch (e) { toast((e as Error).message, "err"); }
    finally { setBusy(false); }
  }

  if (error) return <div role="alert">{error} <button className="btn" onClick={load}>Reintentar</button></div>;
  if (!users) return <p>Cargando usuarios…</p>;
  return <>
    <h2>Usuarios</h2>
    <p>Cuentas individuales del panel. Solo el owner crea, edita, desactiva, resetea contraseñas y cierra sesiones; el servidor lo valida en cada petición. Siempre debe quedar al menos un owner activo. Las cuentas no se borran: se desactivan (su historial y auditoría se conservan).</p>
    {secret && <div className="card" role="status">
      <b>Contraseña temporal de {secret.email}</b> (se muestra solo ahora; compártela por un canal seguro):
      <div style={{ margin: "8px 0" }}><code style={{ fontSize: 16 }}>{secret.password}</code></div>
      <button className="btn btn-ghost" onClick={() => setSecret(null)}>Ya la copié</button>
    </div>}
    {isOwner && !draft && <button className="btn" onClick={() => { setEditing(false); setDraft(empty()); }}>Nuevo usuario</button>}
    {isOwner && draft && <UserForm draft={draft} roles={roles} editing={editing} busy={busy} onChange={setDraft}
      onSubmit={submit} onCancel={() => setDraft(null)} />}
    <div className="card" style={{ overflowX: "auto" }}>
      <table>
        <thead><tr><th>Usuario</th><th>Rol</th><th>Estado</th><th>Credencial</th><th>Sesiones</th><th>Alcance</th>{isOwner && <th>Acciones</th>}</tr></thead>
        <tbody>{users.map(u => {
          const self = u.email === me?.email;
          const sc = u.access_scope;
          const scopeText = u.role === "owner" ? "Total" : [sc.channels.join("/") || "todos los canales",
            sc.connections.length ? `números ${sc.connections.join(", ")}` : "", sc.sectors.length ? `sectores ${sc.sectors.join(", ")}` : ""].filter(Boolean).join(" · ");
          return <tr key={u.email} style={u.active ? undefined : { opacity: .6 }}>
            <td>{u.name}{self && " (tú)"}<br /><small>{u.email}</small></td>
            <td>{u.role}</td>
            <td>{u.active ? "Activo" : "Desactivado"}</td>
            <td>{!u.has_password ? "Sin contraseña (código compartido)" : u.must_change_password ? "Temporal: debe cambiarla" : "Contraseña propia"}</td>
            <td>{u.active_sessions}</td>
            <td><small>{scopeText}</small></td>
            {isOwner && <td style={{ whiteSpace: "nowrap" }}>
              <button className="btn btn-ghost" disabled={busy} onClick={() => { setEditing(true); setDraft(fromUser(u)); }}>Editar</button>{" "}
              {!self && <button className="btn btn-ghost" disabled={busy} onClick={() => resetPassword(u)}>Resetear contraseña</button>}{" "}
              <button className="btn btn-ghost" disabled={busy} onClick={() => {
                if (window.confirm(`¿Cerrar todas las sesiones de ${u.email}?`)) run("Sesiones cerradas", () => api(path(u.email, "/revoke-sessions"), { method: "POST" }));
              }}>Cerrar sesiones</button>{" "}
              {!self && (u.active
                ? <button className="btn btn-danger" disabled={busy} onClick={() => {
                    if (window.confirm(`¿Desactivar a ${u.email}? No podrá entrar y sus sesiones se cierran al instante.`)) run("Usuario desactivado", () => api(path(u.email, "/deactivate"), { method: "POST" }));
                  }}>Desactivar</button>
                : <button className="btn btn-soft" disabled={busy} onClick={() => run("Usuario reactivado", () => api(path(u.email, "/reactivate"), { method: "POST" }))}>Reactivar</button>)}
            </td>}
          </tr>;
        })}</tbody>
      </table>
      {!isOwner && <p className="usage-note">Solo el owner puede gestionar usuarios y roles.</p>}
    </div>
  </>;
}

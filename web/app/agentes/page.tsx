"use client";
import { useCallback, useEffect, useState } from "react";
import { api, can } from "@/lib/api";
import { useMe } from "@/components/AppFrame";

type Profile = {
  name: string; tone: "professional" | "warm" | "concise";
  length: "short" | "balanced" | "detailed"; emoji: "none" | "discreet" | "natural";
  languages: string[]; channels: string[]; connection_ids: string[]; priority: number;
  capabilities: string[]; knowledge_ids: string[];
};
type Version = { id: string; version: number; profile: Profile; author: string; created_at: string };
type Item = { id: string; latest_version: number; published_version: number | null; enabled: number; latest: Version };
const initial: Profile = { name: "Brasper", tone: "professional", length: "balanced", emoji: "discreet",
  languages: ["es", "pt"], channels: ["whatsapp", "telegram", "webchat"], connection_ids: [], priority: 0,
  capabilities: ["quote", "onboarding", "deposit", "info", "status", "tool", "calendar", "llm"], knowledge_ids: [] };

export default function Agents() {
  const editable = can(useMe(), "tenants:write");
  const [items, setItems] = useState<Item[]>([]);
  const [id, setId] = useState("");
  const [version, setVersion] = useState(0);
  const [form, setForm] = useState<Profile>(initial);
  const [versions, setVersions] = useState<Version[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const load = useCallback(async () => {
    const data = await api<{ profiles: Item[] }>("/api/admin/agent-profiles"); setItems(data.profiles);
  }, []);
  useEffect(() => { load().catch(e => setMessage(String(e))); }, [load]);
  function field<K extends keyof Profile>(key: K, value: Profile[K]) {
    setForm(prev => ({ ...prev, [key]: value })); setDirty(true);
  }
  async function select(item: Item) {
    setId(item.id); setVersion(item.latest_version); setForm(item.latest.profile); setDirty(false); setMessage("");
    try { const data = await api<{ versions: Version[] }>(`/api/admin/agent-profiles/${item.id}/history`); setVersions(data.versions); }
    catch (e) { setMessage(String(e)); }
  }
  async function action(type: "save" | "publish" | "disable", targetVersion = version) {
    setBusy(true); setMessage("");
    try {
      const base = `/api/admin/agent-profiles/${encodeURIComponent(id)}`;
      if (type === "save") {
        const saved = await api<Version>(base, { method: "PUT", body: JSON.stringify({ profile: form, expected_version: version }) });
        setVersion(saved.version); setDirty(false); setVersions(prev => [saved, ...prev]);
        setMessage("Borrador guardado. Publícalo cuando esté listo.");
      } else {
        await api(`${base}/${type}`, { method: "POST", body: JSON.stringify({ version: targetVersion }) });
        setMessage(type === "publish" ? `Versión ${targetVersion} publicada para nuevas conversaciones. Las ya iniciadas conservan su estilo.`
          : "Desactivado para nuevas conversaciones. Las existentes conservan su estilo.");
      }
      await load();
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  }
  const current = items.find(x => x.id === id);
  return <>
    <div className="card-head"><div><h2>Agentes de IA</h2><p className="muted">Personalidad por canal, con versiones y continuidad durante la conversación.</p></div>
      <button className="btn" disabled={!editable || busy} onClick={() => { setId(""); setVersion(0); setForm(initial); setVersions([]); setDirty(false); }}>Nuevo perfil</button></div>
    {message && <p role="status" className="usage-note">{message}</p>}
    <div className="cards">
      <section className="card"><h3>Perfiles</h3>{items.length === 0 && <p>No hay perfiles. Se utiliza el prompt general del bot.</p>}
        {items.map(item => <button key={item.id} className="btn ghost" disabled={busy} onClick={() => select(item)}>
          {item.latest.profile.name} · {item.enabled ? `Publicada v${item.published_version}` : "Sin activar"}
        </button>)}
      </section>
      <section className="card"><h3>{version ? `Editar ${id} · v${version}` : "Crear perfil"}</h3>
        <fieldset disabled={!editable || busy} style={{ border: 0, padding: 0 }}>
          <label className="fld">Identificador<input value={id} disabled={version > 0} maxLength={60} placeholder="brasper-bilingue" onChange={e => setId(e.target.value)} /></label>
          <label className="fld">Nombre del asistente<input value={form.name} maxLength={60} onChange={e => field("name", e.target.value)} /></label>
          <label className="fld">Tono<select value={form.tone} onChange={e => field("tone", e.target.value as Profile["tone"])}>
            <option value="professional">Profesional</option><option value="warm">Cercano y paciente</option><option value="concise">Directo y amable</option></select></label>
          <label className="fld">Extensión<select value={form.length} onChange={e => field("length", e.target.value as Profile["length"])}>
            <option value="short">Breve</option><option value="balanced">Equilibrada</option><option value="detailed">Detallada</option></select></label>
          <label className="fld">Emojis<select value={form.emoji} onChange={e => field("emoji", e.target.value as Profile["emoji"])}>
            <option value="none">Ninguno</option><option value="discreet">Discretos</option><option value="natural">Moderados</option></select></label>
          <p>Idiomas</p>{[["es", "Español"], ["pt", "Português"], ["en", "English"]].map(([code, label]) => <label key={code} style={{ marginRight: 16 }}>
            <input type="checkbox" checked={form.languages.includes(code)} onChange={e => field("languages", e.target.checked ? [...form.languages, code] : form.languages.filter(x => x !== code))} /> {label}</label>)}
          <p>Canales</p>{["whatsapp", "telegram", "webchat"].map(code => <label key={code} style={{ marginRight: 16 }}>
            <input type="checkbox" checked={form.channels.includes(code)} onChange={e => field("channels", e.target.checked ? [...form.channels, code] : form.channels.filter(x => x !== code))} /> {code}</label>)}
          <label className="fld">Conexiones WhatsApp (vacío: todas)<input value={form.connection_ids.join(",")} placeholder="Identificadores separados por comas" onChange={e => field("connection_ids", e.target.value.split(",").map(x => x.trim()).filter(Boolean))} /></label>
          <label className="fld">Prioridad (mayor gana si coinciden perfiles)<input type="number" min={0} max={100} value={form.priority} onChange={e => field("priority", Number(e.target.value))} /></label>
          <p>Capacidades permitidas</p>{[["quote", "Cotizar"], ["onboarding", "Registro"], ["deposit", "Cuentas oficiales"], ["info", "Preguntas frecuentes"], ["status", "Seguimiento"], ["tool", "Integraciones"], ["calendar", "Agenda"], ["llm", "Conversación libre"]].map(([code, label]) => <label key={code} style={{ display: "block" }}>
            <input type="checkbox" checked={form.capabilities.includes(code)} onChange={e => field("capabilities", e.target.checked ? [...form.capabilities, code] : form.capabilities.filter(x => x !== code))} /> {label}</label>)}
          <p className="muted">Solo utiliza capacidades que ya estén habilitadas en el sistema. Si una tarea no está permitida, deriva al asesor.</p>
          <label className="fld">Entradas de conocimiento (vacío: todas las aprobadas)<input value={form.knowledge_ids.join(",")} placeholder="Identificadores de FAQ separados por comas" onChange={e => field("knowledge_ids", e.target.value.split(",").map(x => x.trim()).filter(Boolean))} /></label>
          <p className="muted">Se presenta como asistente virtual. Las reglas de pagos, tasas y promociones se mantienen en las herramientas autorizadas.</p>
          <div className="row"><button className="btn" disabled={!id || !form.name || !form.channels.length || !form.languages.length} onClick={() => action("save")}>Guardar borrador</button>
            <button className="btn ghost" disabled={!version || dirty} onClick={() => action("publish")}>Publicar versión guardada</button>
            <button className="btn ghost" disabled={!current?.enabled} onClick={() => action("disable")}>Desactivar</button></div>
        </fieldset>
      </section>
      {versions.length > 0 && <section className="card"><h3>Historial</h3>{versions.map(v => <div key={v.version} className="row">
        <span>v{v.version} · {v.profile.name} · {v.author} · {new Date(v.created_at).toLocaleString()}</span>
        <button className="btn ghost" disabled={!editable || busy || dirty} onClick={() => action("publish", v.version)}>Usar esta versión</button>
      </div>)}</section>}
    </div>
  </>;
}

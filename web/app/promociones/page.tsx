"use client";
import { useCallback, useEffect, useState } from "react";
import { api, can } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import { wallTime, toInstant } from "@/lib/zoned-time";

type Copy = { text: string; media_id: string | null };
type Rules = { segment: "all" | "first_transfer" | "returning"; timezone: string; minimum_amount: number;
  maximum_amount: number | null; maximum_discount: number | null; priority: number; combination: "exclusive";
  messages: { es: Copy; pt: Copy } };
type Draft = { code: string; discount_percentage: number; max_uses: number; per_user_limit: number;
  origin_currency: string; destination_currency: string; start_date: string; end_date: string; campaign_rules: Rules };
type Item = { id: string; version: number; published_version: number | null; active: boolean; used_count: number; draft: Draft };
type Version = { version: number; draft: Draft; author: string; created_at: string };
type MediaOption = { id: string; published: { version: number; asset: { name: string; language: string; purpose: string } } | null };
const empty = (): Draft => ({ code: "", discount_percentage: 0, max_uses: 0, per_user_limit: 1,
  origin_currency: "PEN", destination_currency: "BRL", start_date: "", end_date: "",
  campaign_rules: { segment: "first_transfer", timezone: "America/Lima", minimum_amount: 0,
    maximum_amount: null, maximum_discount: null, priority: 0, combination: "exclusive",
    messages: { es: { text: "", media_id: null }, pt: { text: "", media_id: null } } } });

export default function Promotions() {
  const editable = can(useMe(), "tenants:write");
  const [items, setItems] = useState<Item[]>([]);
  const [id, setId] = useState("");
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState<Draft>(empty);
  const [history, setHistory] = useState<Version[]>([]);
  const [media, setMedia] = useState<MediaOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => { setItems((await api<{ campaigns: Item[] }>("/api/admin/campaigns")).campaigns); }, []);
  useEffect(() => { Promise.all([load(), api<{ assets: MediaOption[] }>("/api/admin/media-library").then(r => setMedia(r.assets))]).catch(e => setMessage(String(e))); }, [load]);
  function field<K extends keyof Draft>(key: K, value: Draft[K]) { setDraft(x => ({ ...x, [key]: value })); setDirty(true); }
  function rule<K extends keyof Rules>(key: K, value: Rules[K]) { field("campaign_rules", { ...draft.campaign_rules, [key]: value }); }
  async function select(item: Item) {
    setId(item.id); setVersion(item.version); setDraft(item.draft); setDirty(false); setMessage("");
    try { setHistory((await api<{ versions: Version[] }>(`/api/admin/campaigns/${item.id}/history`)).versions); }
    catch (e) { setMessage(String(e)); }
  }
  async function action(kind: "save" | "publish" | "disable", selectedVersion = version) {
    setBusy(true); setMessage("");
    try {
      const base = "/api/admin/campaigns" + (id ? `/${id}` : "");
      if (kind === "save") {
        const saved = await api<{ id: string; version: number }>(base, { method: id ? "PUT" : "POST",
          body: JSON.stringify({ draft, expected_version: version }) });
        setId(saved.id); setVersion(saved.version); setDirty(false);
        setHistory((await api<{ versions: Version[] }>(`/api/admin/campaigns/${saved.id}/history`)).versions);
        setMessage("Borrador guardado. La versión publicada continúa vigente hasta que publiques otra.");
      } else {
        await api(`${base}/${kind}`, { method: "POST", body: kind === "publish" ? JSON.stringify({ version: selectedVersion }) : undefined });
        setMessage(kind === "publish" ? `Versión ${selectedVersion} publicada; se aplicará dentro de su vigencia y condiciones.` : "Campaña desactivada para nuevas aplicaciones.");
      }
      await load();
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  }
  const rules = draft.campaign_rules;
  const current = items.find(x => x.id === id);
  return <>
    <div className="card-head"><div><h2>Promociones</h2><p className="muted">Cupones de Brasper: descuento sobre la comisión, con condiciones verificadas por cliente.</p></div>
      <button className="btn" disabled={!editable || busy} onClick={() => { setId(""); setVersion(0); setDraft(empty()); setHistory([]); setDirty(false); }}>Nueva campaña</button></div>
    {message && <p role="status" className="usage-note">{message}</p>}
    <div className="cards"><section className="card"><h3>Campañas</h3>
      {!items.length && <p>No hay campañas cargadas.</p>}
      {items.map(item => <button className="btn ghost" key={item.id} disabled={busy} onClick={() => select(item)}>
        {item.draft.code} · {item.active ? `Publicada v${item.published_version}` : "Sin activar"} · {item.used_count} usos reservados o consumidos
      </button>)}
    </section><section className="card"><h3>{id ? `Editar ${draft.code} · borrador v${version}` : "Crear borrador"}</h3>
      <form onSubmit={e => { e.preventDefault(); action("save"); }}><fieldset disabled={!editable || busy} style={{ border: 0, padding: 0 }}>
        <label className="fld">Código<input required pattern="[A-Za-z0-9_-]+" maxLength={80} disabled={!!id} value={draft.code} onChange={e => field("code", e.target.value)} /></label>
        <label className="fld">Clientes<select value={rules.segment} onChange={e => rule("segment", e.target.value as Rules["segment"])}>
          <option value="first_transfer">Primer envío</option><option value="returning">Con envíos completados</option><option value="all">Todos los clientes identificados</option></select></label>
        <label className="fld">Descuento sobre comisión (%)<input required type="number" min={0} max={100} step="0.01" value={draft.discount_percentage} onChange={e => field("discount_percentage", Number(e.target.value))} /></label>
        <label className="fld">Usos totales máximos<input required type="number" min={1} step={1} value={draft.max_uses || ""} onChange={e => field("max_uses", Number(e.target.value))} /></label>
        <label className="fld">Usos máximos por cliente<input required type="number" min={1} step={1} value={draft.per_user_limit} onChange={e => field("per_user_limit", Number(e.target.value))} /></label>
        <div className="row">{(["origin_currency", "destination_currency"] as const).map((key, i) => <label className="fld" key={key}>{i ? "Moneda de destino" : "Moneda de origen"}
          <select value={draft[key]} onChange={e => field(key, e.target.value)}>{["PEN", "BRL", "USD"].map(c => <option key={c}>{c}</option>)}</select></label>)}</div>
        <label className="fld">Zona horaria<select value={rules.timezone} onChange={e => rule("timezone", e.target.value)}>
          <option value="America/Lima">Perú · Lima</option><option value="America/Sao_Paulo">Brasil · São Paulo</option></select></label>
        {(["start_date", "end_date"] as const).map((key, i) => <label className="fld" key={key}>{i ? "Fin" : "Inicio"} ({rules.timezone})
          <input required type="datetime-local" value={wallTime(draft[key], rules.timezone)} onChange={e => { try { field(key, toInstant(e.target.value, rules.timezone)); } catch (err) { setMessage(String(err)); } }} /></label>)}
        <label className="fld">Monto mínimo de envío ({draft.origin_currency})<input type="number" min={0} step="0.01" value={rules.minimum_amount} onChange={e => rule("minimum_amount", Number(e.target.value))} /></label>
        {(["maximum_amount", "maximum_discount"] as const).map((key, i) => <label className="fld" key={key}>{i ? "Tope de descuento" : "Monto máximo de envío"} ({draft.origin_currency}, vacío: sin tope)
          <input type="number" min={i ? 0 : 0.01} step="0.01" value={rules[key] ?? ""} onChange={e => rule(key, e.target.value === "" ? null : Number(e.target.value))} /></label>)}
        <label className="fld">Prioridad (mayor primero)<input type="number" min={0} max={100} step={1} value={rules.priority} onChange={e => rule("priority", Number(e.target.value))} /></label>
        <p className="muted">Se aplica una campaña por operación. Si empatan en prioridad, gana el mayor ahorro. El primer envío se reserva al registrar una operación pendiente; cotizar no consume el cupón.</p>
        {(["es", "pt"] as const).map(lang => <div key={lang}><label className="fld">Condiciones aprobadas · {lang === "es" ? "Español" : "Português"}
          <textarea required maxLength={2000} rows={4} value={rules.messages[lang].text} onChange={e => rule("messages", { ...rules.messages, [lang]: { ...rules.messages[lang], text: e.target.value } })} /></label>
          <label className="fld">Imagen aprobada (opcional)<select value={rules.messages[lang].media_id ?? ""} onChange={e => rule("messages", { ...rules.messages, [lang]: { ...rules.messages[lang], media_id: e.target.value || null } })}>
            <option value="">Solo texto</option>{media.filter(m => m.published?.asset.language === lang && m.published?.asset.purpose === "promotion").map(m => <option key={m.id} value={m.id}>{m.published!.asset.name} · v{m.published!.version}</option>)}
            {rules.messages[lang].media_id && !media.some(m => m.id === rules.messages[lang].media_id && m.published?.asset.language === lang && m.published?.asset.purpose === "promotion") && <option value={rules.messages[lang].media_id!}>Imagen retirada o sin aprobar: selecciona otra</option>}
          </select></label><a href="/biblioteca">Subir o aprobar imágenes</a></div>)}
        <div className="row"><button className="btn" type="submit">Guardar borrador</button>
          <button className="btn ghost" type="button" disabled={!id || dirty} onClick={() => action("publish")}>Publicar versión guardada</button>
          <button className="btn ghost" type="button" disabled={!current?.active} onClick={() => action("disable")}>Desactivar</button></div>
      </fieldset></form>
    </section>{history.length > 0 && <section className="card"><h3>Versiones guardadas</h3>{history.map(v => <div className="row" key={v.version}>
      <span>v{v.version} · {v.draft.discount_percentage}% · {v.author} · {new Date(v.created_at).toLocaleString()}</span>
      <button className="btn ghost" disabled={!editable || busy || dirty} onClick={() => action("publish", v.version)}>Publicar esta versión</button>
    </div>)}</section>}</div>
  </>;
}

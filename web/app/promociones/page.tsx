"use client";
import { useCallback, useEffect, useState } from "react";
import { api, API_BASE, can, getToken } from "@/lib/api";
import { useMe } from "@/components/AppFrame";
import { wallTime, toInstant } from "@/lib/zoned-time";

type Lang = "es" | "pt";
type Copy = { text: string; media_id: string | null };
type Rules = { segment: "all" | "first_transfer" | "returning"; timezone: string; minimum_amount: number;
  maximum_amount: number | null; maximum_discount: number | null; priority: number; combination: "exclusive";
  messages: { es: Copy; pt: Copy } };
type Draft = { code?: string | null; name: string; discount_percentage: number; max_uses: number | null; per_user_limit: number;
  routes: string[]; origin_currency?: string | null; destination_currency?: string | null;
  start_date: string; end_date: string; campaign_rules: Rules };
type Item = { id: string; version: number; published_version: number | null; active: boolean; used_count: number; draft: Draft };
type Version = { version: number; draft: Draft; author: string; created_at: string };
type MediaOption = { id: string; published: { version: number; asset: { name: string; language: string; purpose: string } } | null };

const LANGS: { code: Lang; label: string }[] = [{ code: "es", label: "Español" }, { code: "pt", label: "Português" }];
const SEGMENTS: Record<Rules["segment"], string> = {
  first_transfer: "Primer envío (un beneficio por persona)", returning: "Clientes con envíos completados", all: "Todos los clientes identificados" };
const DISCLAIMER: Record<Lang, string> = {
  es: "Beneficio sujeto a comprobación: se aplica solo si tu identidad y tu historial de envíos lo confirman al cotizar con tu cuenta Brasper.",
  pt: "Benefício sujeito a verificação: só se aplica se a sua identidade e o seu histórico de envios o confirmarem ao cotar com a sua conta Brasper." };

const empty = (): Draft => ({ code: null, name: "", discount_percentage: 10, max_uses: 100, per_user_limit: 1, routes: [],
  start_date: "", end_date: "",
  campaign_rules: { segment: "first_transfer", timezone: "America/Lima", minimum_amount: 0,
    maximum_amount: null, maximum_discount: null, priority: 0, combination: "exclusive",
    messages: { es: { text: "", media_id: null }, pt: { text: "", media_id: null } } } });

// Campañas guardadas antes de las rutas múltiples traen un par único.
function normalize(draft: Draft): Draft {
  const routes = draft.routes?.length ? draft.routes
    : draft.origin_currency && draft.destination_currency ? [`${draft.origin_currency}_${draft.destination_currency}`] : [];
  return { ...empty(), ...draft, name: draft.name ?? "", routes };
}
const multiOrigin = (routes: string[]) => routes.includes("ALL") || new Set(routes.map(r => r.slice(0, 3))).size > 1;
const routeLabel = (r: string) => (r === "ALL" ? "Todas las rutas" : r.replace("_", " → "));

function problems(draft: Draft): string[] {
  const out: string[] = [];
  if (!draft.name.trim()) out.push("Escribe un nombre para la promoción.");
  if (!draft.routes.length) out.push("Elige al menos una ruta o todas las rutas.");
  if (!(draft.discount_percentage >= 1 && draft.discount_percentage <= 100)) out.push("El descuento debe estar entre 1 y 100 %.");
  if (!draft.start_date || !draft.end_date || draft.end_date <= draft.start_date) out.push("Indica inicio y fin, con el fin posterior al inicio.");
  for (const { code, label } of LANGS) if (!draft.campaign_rules.messages[code].text.trim()) out.push(`Falta el mensaje en ${label}.`);
  if (draft.campaign_rules.segment === "first_transfer" && draft.per_user_limit !== 1) out.push("Primer envío admite un único beneficio por persona.");
  if (Math.abs(Math.round(draft.discount_percentage * 100) - draft.discount_percentage * 100) > 1e-9) out.push("El porcentaje admite como máximo dos decimales.");
  const r = draft.campaign_rules;
  if (multiOrigin(draft.routes) && (r.minimum_amount || r.maximum_amount !== null || r.maximum_discount !== null))
    out.push("Con varias monedas de origen deja vacíos mínimo, máximo y tope (una misma cifra no vale igual en PEN, BRL o USD).");
  return out;
}

function summary(draft: Draft): string {
  const r = draft.campaign_rules;
  return [`${draft.name || "Sin nombre"}: ${draft.discount_percentage}% de descuento sobre la comisión`,
    `Clientes: ${SEGMENTS[r.segment]}`, `Rutas: ${draft.routes.map(routeLabel).join(", ") || "ninguna"}`,
    `Vigencia: ${draft.start_date ? new Date(draft.start_date).toLocaleString() : "?"} → ${draft.end_date ? new Date(draft.end_date).toLocaleString() : "?"} (${r.timezone})`,
    `Cupo total: ${draft.max_uses ?? "sin límite"} · Por persona: ${draft.per_user_limit}`,
    `Monto mínimo: ${r.minimum_amount}${r.maximum_amount ? ` · máximo: ${r.maximum_amount}` : ""}${r.maximum_discount ? ` · tope de descuento: ${r.maximum_discount}` : ""}`,
  ].join("\n");
}

function Preview({ draft, media }: { draft: Draft; media: MediaOption[] }) {
  const [images, setImages] = useState<Record<string, string>>({});
  const ids = LANGS.map(l => draft.campaign_rules.messages[l.code].media_id ?? "").join("|");
  useEffect(() => {
    let alive = true; const urls: string[] = [];
    (async () => {
      const next: Record<string, string> = {};
      for (const { code } of LANGS) {
        const id = draft.campaign_rules.messages[code].media_id;
        const item = media.find(m => m.id === id && m.published?.asset.language === code && m.published?.asset.purpose === "promotion");
        if (!id || !item?.published) continue;
        const res = await fetch(`${API_BASE}/api/admin/media-library/${id}/${item.published.version}/preview`, { headers: { "X-Auth-Token": getToken() } });
        if (res.ok) { const url = URL.createObjectURL(await res.blob()); urls.push(url); next[code] = url; }
      }
      if (alive) setImages(next);
    })().catch(() => undefined);
    return () => { alive = false; urls.forEach(u => URL.revokeObjectURL(u)); };
  }, [ids, media]); // eslint-disable-line react-hooks/exhaustive-deps
  return <section className="card"><h3>Vista previa para el cliente</h3>
    <p className="muted">Así se ve en el chat. Cada idioma usa solo su texto y su imagen; el bot pregunta el idioma si no está claro.</p>
    <div className="cards">{LANGS.map(({ code, label }) => <div key={code} className="card">
      <b>{label}</b>
      {images[code] ? <img src={images[code]} alt={`Imagen de la promoción en ${label}`} style={{ maxWidth: "100%", maxHeight: 240, objectFit: "contain", display: "block", margin: "8px 0" }} />
        : <p className="muted">{draft.campaign_rules.messages[code].media_id ? "Imagen no aprobada en este idioma: se enviará solo el texto." : "Sin imagen: solo texto."}</p>}
      <p style={{ whiteSpace: "pre-wrap" }}>{draft.campaign_rules.messages[code].text || <span className="muted">(sin mensaje)</span>}</p>
      <p className="muted" style={{ whiteSpace: "pre-wrap" }}>{DISCLAIMER[code]}</p>
    </div>)}</div>
    <p className="muted" style={{ whiteSpace: "pre-wrap" }}>{summary(draft)}</p>
  </section>;
}

export default function Promotions() {
  const editable = can(useMe(), "tenants:write");
  const [items, setItems] = useState<Item[]>([]);
  const [routes, setRoutes] = useState<string[]>([]);
  const [id, setId] = useState("");
  const [version, setVersion] = useState(0);
  const [draft, setDraft] = useState<Draft>(empty);
  const [history, setHistory] = useState<Version[]>([]);
  const [media, setMedia] = useState<MediaOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [message, setMessage] = useState("");
  const load = useCallback(async () => { setItems((await api<{ campaigns: Item[] }>("/api/admin/campaigns")).campaigns); }, []);
  useEffect(() => {
    Promise.all([load(), api<{ assets: MediaOption[] }>("/api/admin/media-library").then(r => setMedia(r.assets)),
      api<{ routes: string[] }>("/api/admin/campaigns/routes").then(r => setRoutes(r.routes))]).catch(e => setMessage(String(e)));
  }, [load]);
  function field<K extends keyof Draft>(key: K, value: Draft[K]) { setDraft(x => ({ ...x, [key]: value })); setDirty(true); }
  function rule<K extends keyof Rules>(key: K, value: Rules[K]) {
    setDraft(x => {
      const next = { ...x, campaign_rules: { ...x.campaign_rules, [key]: value } };
      if (key === "segment" && value === "first_transfer") next.per_user_limit = 1;
      return next;
    });
    setDirty(true);
  }
  function toggleRoute(route: string, on: boolean) {
    if (route === "ALL") return field("routes", on ? ["ALL"] : []);
    const rest = draft.routes.filter(r => r !== "ALL" && r !== route);
    field("routes", on ? [...rest, route].sort() : rest);
  }
  async function select(item: Item) {
    setId(item.id); setVersion(item.version); setDraft(normalize(item.draft)); setDirty(false); setMessage("");
    try { setHistory((await api<{ versions: Version[] }>(`/api/admin/campaigns/${item.id}/history`)).versions); }
    catch (e) { setMessage(String(e)); }
  }
  async function action(kind: "save" | "publish" | "disable", selectedVersion = version) {
    if (kind === "publish") {
      const target = kind === "publish" && selectedVersion !== version ? normalize(history.find(v => v.version === selectedVersion)?.draft ?? draft) : draft;
      const issues = problems(target);
      if (issues.length) { setMessage("No se puede publicar:\n" + issues.join("\n")); return; }
      if (!window.confirm(`Publicar la versión ${selectedVersion}:\n\n${summary(target)}\n\nSe aplicará solo dentro de su vigencia y condiciones. Publicar no envía mensajes masivos.`)) return;
    }
    if (kind === "disable" && !window.confirm("¿Desactivar la promoción? Dejará de ofrecerse y de aplicarse a nuevas operaciones.")) return;
    setBusy(true); setMessage("");
    try {
      const base = "/api/admin/campaigns" + (id ? `/${id}` : "");
      if (kind === "save") {
        const body = { ...draft, code: id ? draft.code : null };
        const saved = await api<{ id: string; version: number }>(base, { method: id ? "PUT" : "POST",
          body: JSON.stringify({ draft: body, expected_version: version }) });
        setId(saved.id); setVersion(saved.version); setDirty(false);
        setHistory((await api<{ versions: Version[] }>(`/api/admin/campaigns/${saved.id}/history`)).versions);
        setMessage("Borrador guardado. Los clientes no lo ven: la versión publicada sigue vigente hasta que publiques otra.");
      } else {
        await api(`${base}/${kind}`, { method: "POST", body: kind === "publish" ? JSON.stringify({ version: selectedVersion }) : undefined });
        setMessage(kind === "publish" ? `Versión ${selectedVersion} publicada.` : "Promoción desactivada para nuevas operaciones.");
      }
      await load();
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  }
  const rules = draft.campaign_rules;
  const current = items.find(x => x.id === id);
  const firstTransfer = rules.segment === "first_transfer";
  const issues = problems(draft);
  return <>
    <div className="card-head"><div><h2>Promociones</h2><p className="muted">Descuento sobre la comisión, administrado en la plataforma IA. La elegibilidad se comprueba con datos de Brasper; el asesor reserva el beneficio al registrar la operación y el cobro final lo registra Brasper.</p></div>
      <button className="btn" disabled={!editable || busy} onClick={() => { setId(""); setVersion(0); setDraft(empty()); setHistory([]); setDirty(false); setMessage(""); }}>Nueva promoción</button></div>
    {message && <p role="status" className="usage-note" style={{ whiteSpace: "pre-wrap" }}>{message}</p>}
    <div className="cards"><section className="card"><h3>Promociones</h3>
      {!items.length && <p>No hay promociones cargadas.</p>}
      {items.map(item => <button className="btn ghost" key={item.id} disabled={busy} onClick={() => select(item)}>
        {item.draft.name || item.draft.code} · {item.active ? `Publicada v${item.published_version}` : "Sin publicar"} · {item.used_count} usos reservados o consumidos
      </button>)}
    </section><section className="card"><h3>{id ? `Editar ${draft.name || draft.code} · borrador v${version}` : "Nueva promoción"}</h3>
      <form onSubmit={e => { e.preventDefault(); action("save"); }}><fieldset disabled={!editable || busy} style={{ border: 0, padding: 0 }}>
        <label className="fld">Nombre<input required maxLength={120} value={draft.name} onChange={e => field("name", e.target.value)} placeholder="Ej. Primer envío octubre" /></label>
        {draft.code && <p className="muted">Identificador interno: <code>{draft.code}</code> (generado por Brasper; no cambia).</p>}
        <label className="fld">Clientes<select value={rules.segment} onChange={e => rule("segment", e.target.value as Rules["segment"])}>
          {Object.entries(SEGMENTS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label className="fld">Descuento sobre la comisión (1–100 %)<input required type="number" min={1} max={100} step="0.01" value={draft.discount_percentage} onChange={e => field("discount_percentage", Number(e.target.value))} /></label>
        <label className="fld">Cupo total de la promoción (todas las personas)<input type="number" min={1} step={1} disabled={draft.max_uses === null} value={draft.max_uses ?? ""} onChange={e => field("max_uses", Number(e.target.value))} /></label>
        <label><input type="checkbox" checked={draft.max_uses === null} onChange={e => field("max_uses", e.target.checked ? null : 100)} /> Sin límite global (propuesta de producto: confirmar antes de publicar)</label>
        <label className="fld">Beneficios por persona<input required type="number" min={1} step={1} disabled={firstTransfer} value={draft.per_user_limit} onChange={e => field("per_user_limit", Number(e.target.value))} /></label>
        {firstTransfer && <p className="muted">Primer envío: un único beneficio por persona, comprobado con sus envíos completados en Brasper. Se reserva con la operación pendiente, se consume al completarla y se libera si falla.</p>}
        <fieldset className="fld" style={{ border: 0, padding: 0 }}><legend>Rutas</legend>
          {!routes.length && <p className="muted">No se pudieron cargar las rutas habilitadas de Brasper.</p>}
          {routes.length > 0 && <label><input type="checkbox" checked={draft.routes.includes("ALL")} onChange={e => toggleRoute("ALL", e.target.checked)} /> Todas las rutas habilitadas</label>}
          {draft.routes.includes("ALL") && <p className="muted">«Todas» se evalúa contra las rutas habilitadas en Brasper en el momento de cada cotización.</p>}
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12 }}>{routes.map(r => <label key={r}>
            <input type="checkbox" disabled={draft.routes.includes("ALL")} checked={draft.routes.includes(r) || draft.routes.includes("ALL")} onChange={e => toggleRoute(r, e.target.checked)} /> {routeLabel(r)}</label>)}</div>
          {draft.routes.filter(r => r !== "ALL" && routes.length && !routes.includes(r)).map(r => <p key={r} className="usage-note">La ruta {routeLabel(r)} ya no está habilitada en Brasper: quítala antes de guardar.</p>)}
        </fieldset>
        <label className="fld">Zona horaria<select value={rules.timezone} onChange={e => rule("timezone", e.target.value)}>
          <option value="America/Lima">Perú · Lima</option><option value="America/Sao_Paulo">Brasil · São Paulo</option></select></label>
        {(["start_date", "end_date"] as const).map((key, i) => <label className="fld" key={key}>{i ? "Fin" : "Inicio"} ({rules.timezone})
          <input required type="datetime-local" value={wallTime(draft[key], rules.timezone)} onChange={e => { try { field(key, toInstant(e.target.value, rules.timezone)); } catch (err) { setMessage(String(err)); } }} /></label>)}
        {multiOrigin(draft.routes) && <p className="muted">Varias monedas de origen: mínimo, máximo y tope quedan vacíos. Para usarlos elige rutas con una sola moneda de origen.</p>}
        <label className="fld">Monto mínimo de envío{!multiOrigin(draft.routes) && draft.routes[0] ? ` (${draft.routes[0].slice(0, 3)})` : ""}<input type="number" min={0} step="0.01" disabled={multiOrigin(draft.routes)} value={rules.minimum_amount} onChange={e => rule("minimum_amount", Number(e.target.value))} /></label>
        {(["maximum_amount", "maximum_discount"] as const).map((key, i) => <label className="fld" key={key}>{i ? "Tope de descuento" : "Monto máximo de envío"} (vacío: sin tope)
          <input type="number" min={i ? 0 : 0.01} step="0.01" disabled={multiOrigin(draft.routes)} value={rules[key] ?? ""} onChange={e => rule(key, e.target.value === "" ? null : Number(e.target.value))} /></label>)}
        <label className="fld">Prioridad (mayor primero)<input type="number" min={0} max={100} step={1} value={rules.priority} onChange={e => rule("priority", Number(e.target.value))} /></label>
        <p className="muted">Se aplica una promoción por operación. Si empatan en prioridad, gana el mayor ahorro. Cotizar no reserva el beneficio.</p>
        {LANGS.map(({ code, label }) => <div key={code}><label className="fld">Mensaje y condiciones · {label}
          <textarea required maxLength={2000} rows={4} value={rules.messages[code].text} onChange={e => rule("messages", { ...rules.messages, [code]: { ...rules.messages[code], text: e.target.value } })} /></label>
          <label className="fld">Imagen aprobada en {label} (opcional)<select value={rules.messages[code].media_id ?? ""} onChange={e => rule("messages", { ...rules.messages, [code]: { ...rules.messages[code], media_id: e.target.value || null } })}>
            <option value="">Solo texto</option>{media.filter(m => m.published?.asset.language === code && m.published?.asset.purpose === "promotion").map(m => <option key={m.id} value={m.id}>{m.published!.asset.name} · v{m.published!.version}</option>)}
            {rules.messages[code].media_id && !media.some(m => m.id === rules.messages[code].media_id && m.published?.asset.language === code && m.published?.asset.purpose === "promotion") && <option value={rules.messages[code].media_id!}>Imagen retirada o sin aprobar: selecciona otra</option>}
          </select></label><a href="/biblioteca">Subir o aprobar imágenes</a></div>)}
        {issues.length > 0 && <ul className="muted">{issues.map(i => <li key={i}>{i}</li>)}</ul>}
        <div className="row"><button className="btn" type="submit">Guardar borrador</button>
          <button className="btn ghost" type="button" disabled={!id || dirty || issues.length > 0} onClick={() => action("publish")}>Publicar versión guardada</button>
          <button className="btn ghost" type="button" disabled={!current?.active} onClick={() => action("disable")}>Desactivar</button></div>
        {dirty && id && <p className="muted">Hay cambios sin guardar: guarda el borrador antes de publicar.</p>}
      </fieldset></form>
    </section>
    <Preview draft={draft} media={media} />
    {history.length > 0 && <section className="card"><h3>Versiones guardadas</h3>{history.map(v => <div className="row" key={v.version}>
      <span>v{v.version} · {v.draft.discount_percentage}% · {v.author} · {new Date(v.created_at).toLocaleString()}{current?.published_version === v.version ? " · publicada" : ""}</span>
      <button className="btn ghost" disabled={!editable || busy || dirty} onClick={() => action("publish", v.version)}>Publicar esta versión</button>
    </div>)}</section>}</div>
  </>;
}

"use client";
import { useCallback, useEffect, useState } from "react";
import { api, API_BASE, can, getToken } from "@/lib/api";
import { useMe } from "@/components/AppFrame";

type Asset = { name: string; purpose: string; language: string; description: string };
type Version = { asset_id: string; version: number; asset: Asset; author: string; created_at: string };
type Item = { id: string; latest_version: number; published_version: number | null; enabled: number; latest: Version };
const initial = (): Asset => ({ name: "", purpose: "promotion", language: "es", description: "" });

export default function Library() {
  const editable = can(useMe(), "tenants:write");
  const [items, setItems] = useState<Item[]>([]);
  const [id, setId] = useState("");
  const [version, setVersion] = useState(0);
  const [asset, setAsset] = useState<Asset>(initial);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [history, setHistory] = useState<Version[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [dirty, setDirty] = useState(false);
  const load = useCallback(async () => setItems((await api<{ assets: Item[] }>("/api/admin/media-library")).assets), []);
  useEffect(() => { load().catch(e => setMessage(String(e))); }, [load]);
  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview); }, [preview]);
  function field(key: keyof Asset, value: string) { setAsset(a => ({ ...a, [key]: value })); setDirty(true); }
  async function select(item: Item) {
    setId(item.id); setVersion(item.latest_version); setAsset(item.latest.asset); setFile(null); setDirty(false); setMessage("");
    try {
      setHistory((await api<{ versions: Version[] }>(`/api/admin/media-library/${item.id}/history`)).versions);
      const response = await fetch(`${API_BASE}/api/admin/media-library/${item.id}/${item.latest_version}/preview`, { headers: { "X-Auth-Token": getToken() } });
      if (!response.ok) throw new Error("No se pudo cargar la imagen");
      setPreview(URL.createObjectURL(await response.blob()));
    } catch (e) { setMessage(String(e)); }
  }
  async function action(kind: "save" | "publish" | "disable", selected = version) {
    setBusy(true); setMessage("");
    try {
      const base = `/api/admin/media-library/${id}`;
      if (kind === "save") {
        if (!file) throw new Error("Selecciona la imagen de esta versión");
        const form = new FormData(); form.append("file", file); form.append("metadata", JSON.stringify(asset)); form.append("expected_version", String(version));
        const saved = await api<Version>(base, { method: "PUT", body: form });
        setVersion(saved.version); setDirty(false); setHistory(h => [saved, ...h]); setFile(null);
        setMessage("Borrador guardado. Revisa la imagen antes de aprobarla.");
      } else {
        await api(`${base}/${kind}`, { method: "POST", body: JSON.stringify({ version: selected }) });
        setMessage(kind === "publish" ? "Imagen aprobada para su propósito e idioma." : "Imagen retirada de nuevos envíos automáticos.");
      }
      await load();
    } catch (e) { setMessage(String(e)); }
    finally { setBusy(false); }
  }
  return <>
    <div className="card-head"><div><h2>Biblioteca de imágenes</h2><p className="muted">Material público aprobado para promociones e instrucciones. Los comprobantes de clientes se gestionan en su conversación.</p></div>
      <button className="btn" disabled={!editable || busy} onClick={() => { setId(""); setVersion(0); setAsset(initial()); setFile(null); setPreview(""); setHistory([]); setDirty(false); }}>Nueva imagen</button></div>
    {message && <p role="status">{message}</p>}
    <div className="cards"><section className="card"><h3>Materiales</h3>{!items.length && <p>No hay imágenes guardadas.</p>}
      {items.map(item => <button className="btn ghost" key={item.id} disabled={busy} onClick={() => select(item)}>{item.latest.asset.name} · {item.latest.asset.language} · {item.enabled ? `Aprobada v${item.published_version}` : "Sin aprobar"}</button>)}
    </section><section className="card"><h3>{version ? `Editar ${id} · v${version}` : "Nuevo borrador"}</h3>
      <form onSubmit={e => { e.preventDefault(); action("save"); }}><fieldset disabled={!editable || busy} style={{ border: 0, padding: 0 }}>
        <label className="fld">Identificador<input required pattern="[a-zA-Z0-9_-]{1,60}" value={id} disabled={version > 0} onChange={e => setId(e.target.value)} /></label>
        <label className="fld">Nombre<input required maxLength={100} value={asset.name} onChange={e => field("name", e.target.value)} /></label>
        <label className="fld">Propósito<select value={asset.purpose} onChange={e => field("purpose", e.target.value)}>
          <option value="promotion">Promoción</option><option value="instructions">Instrucciones</option><option value="official_accounts">Cuentas oficiales</option></select></label>
        <label className="fld">Idioma<select value={asset.language} onChange={e => field("language", e.target.value)}><option value="es">Español</option><option value="pt">Português</option></select></label>
        <label className="fld">Descripción<textarea maxLength={1000} value={asset.description} onChange={e => field("description", e.target.value)} /></label>
        <label className="fld">Imagen PNG o JPEG (hasta 5 MB)<input type="file" accept="image/png,image/jpeg" onChange={e => {
          const f = e.target.files?.[0]; if (!f) return;
          if (f.size > 5 * 1024 * 1024) { setMessage("La imagen supera 5 MB"); return; }
          setFile(f); setPreview(URL.createObjectURL(f)); setDirty(true);
        }} /></label>
        {preview && <img src={preview} alt={asset.description || asset.name || "Vista previa"} style={{ maxWidth: "100%", maxHeight: 360, objectFit: "contain" }} />}
        <div className="row"><button className="btn" type="submit" disabled={!file}>Guardar borrador</button>
          <button className="btn ghost" type="button" disabled={!version || dirty} onClick={() => action("publish")}>Aprobar versión guardada</button>
          <button className="btn ghost" type="button" disabled={!items.find(x => x.id === id)?.enabled} onClick={() => action("disable")}>Retirar aprobación</button></div>
      </fieldset></form></section>
      {history.length > 0 && <section className="card"><h3>Historial</h3>{history.map(v => <div className="row" key={v.version}>
        <span>v{v.version} · {v.asset.name} · {v.author}</span><button className="btn ghost" disabled={!editable || busy || dirty} onClick={() => action("publish", v.version)}>Aprobar esta versión</button>
      </div>)}</section>}</div>
  </>;
}

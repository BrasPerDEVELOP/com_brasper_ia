"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, can, DeletionRequest, DocOverview, PublicDocument } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import { useMe } from "@/components/AppFrame";
import { useToast } from "@/components/Toast";
import Icon from "@/components/Icon";

const SLUG_LABEL: Record<string, string> = { privacidad: "Política de privacidad", terminos: "Términos y condiciones", "eliminacion-de-datos": "Eliminación de datos" };
const TEMPLATE: Record<string, string> = {
  privacidad: "# Política de privacidad\n\n_Borrador: completar y aprobar con el responsable de Brasper antes de publicar._\n\n## Responsable\n\n## Datos que tratamos\n\n## Finalidades\n\n## Proveedores y encargados (IA, mensajería)\n\n## Conservación\n\n## Tus derechos y cómo ejercerlos\n",
  terminos: "# Términos y condiciones\n\n_Borrador: completar y aprobar antes de publicar._\n\n## Servicio\n\n## Uso del chat y del asistente\n\n## Cotizaciones y operaciones\n\n## Responsabilidad\n",
  "eliminacion-de-datos": "# Eliminación de datos\n\n_Borrador: completar y aprobar antes de publicar._\n\n## Qué datos puedes pedir eliminar\n\n## Qué registros debemos conservar y por qué\n\n## Cómo solicitarlo\n\nUsa el formulario de esta página o escríbenos por el mismo canal en que nos contactaste. Verificaremos tu identidad antes de eliminar información.\n",
};
const DEL_STATUS: Record<string, { label: string; cls: string }> = {
  received: { label: "Recibida", cls: "info" }, verifying: { label: "Verificando identidad", cls: "warn" },
  completed: { label: "Completada", cls: "ok" }, rejected: { label: "Rechazada", cls: "closed" },
};

export default function Documentos() {
  const me = useMe();
  const { toast } = useToast();
  const canEdit = can(me, "tenants:write");
  const [overview, setOverview] = useState<DocOverview[]>([]);
  const [slug, setSlug] = useState("privacidad");
  const [lang, setLang] = useState<"es" | "pt">("es");
  const [latest, setLatest] = useState<PublicDocument | null>(null);
  const [published, setPublished] = useState<PublicDocument | null>(null);
  const [history, setHistory] = useState<PublicDocument[]>([]);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [busy, setBusy] = useState(false);
  const [loadingDoc, setLoadingDoc] = useState(true);
  const [docError, setDocError] = useState("");
  const [edited, setEdited] = useState(false);
  const requestVersion = useRef(0);
  const [requests, setRequests] = useState<DeletionRequest[]>([]);

  const loadOverview = useCallback(() => api<{ documents: DocOverview[] }>("/api/admin/documents").then(d => setOverview(d.documents)).catch(() => {}), []);
  const loadDoc = useCallback(() => {
    const request = ++requestVersion.current;
    setLoadingDoc(true); setDocError("");
    api<{ latest: PublicDocument | null; published: PublicDocument | null; history: PublicDocument[] }>(`/api/admin/documents/${slug}?lang=${lang}`)
      .then(d => {
        if (request !== requestVersion.current) return;
        setLatest(d.latest); setPublished(d.published); setHistory(d.history);
        setTitle(d.latest?.title || SLUG_LABEL[slug]);
        setBody(d.latest?.body_md || TEMPLATE[slug] || "");
        setEdited(false);
      }).catch(e => {
        if (request === requestVersion.current) setDocError((e as Error).message);
      }).finally(() => {
        if (request === requestVersion.current) setLoadingDoc(false);
      });
  }, [slug, lang]);
  const loadRequests = useCallback(() => {
    if (!canEdit) return;
    api<{ requests: DeletionRequest[] }>("/api/admin/deletion-requests").then(d => setRequests(d.requests)).catch(() => {});
  }, [canEdit]);

  useEffect(() => { loadOverview(); loadRequests(); }, [loadOverview, loadRequests]);
  useEffect(() => { loadDoc(); return () => { requestVersion.current++; }; }, [loadDoc]);
  useEffect(() => {
    if (!edited) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [edited]);

  const dirty = useMemo(() => (latest ? latest.title !== title || latest.body_md !== body : body.trim().length > 0), [latest, title, body]);

  function selectDoc(nextSlug: string, nextLang: "es" | "pt") {
    if (busy || (nextSlug === slug && nextLang === lang)) return;
    if (edited && !window.confirm("Hay cambios sin guardar. ¿Quieres descartarlos y abrir otro documento?")) return;
    requestVersion.current++;
    setLoadingDoc(true); setEdited(false); setDocError("");
    setLatest(null); setPublished(null); setHistory([]); setTitle(""); setBody("");
    setSlug(nextSlug); setLang(nextLang);
  }

  async function saveDraft() {
    if (busy || loadingDoc || docError) return;
    setBusy(true);
    try {
      await api(`/api/admin/documents/${slug}`, { method: "PUT", body: JSON.stringify({ lang, title, body_md: body, expected_version: latest?.version ?? 0 }) });
      toast("Borrador guardado (no es público)", "ok");
      loadDoc(); loadOverview();
    } catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }
  async function publish() {
    if (busy || loadingDoc || docError || dirty) return;
    if (!latest || latest.status !== "draft") { toast("Guarda un borrador antes de publicar", "warn"); return; }
    setBusy(true);
    try {
      await api(`/api/admin/documents/${slug}/publish`, { method: "POST", body: JSON.stringify({ lang, version: latest.version }) });
      toast(`Publicada la versión ${latest.version}`, "ok");
      loadDoc(); loadOverview();
    } catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }
  async function setReqStatus(id: number, status: string) {
    try {
      await api(`/api/admin/deletion-requests/${id}/status`, { method: "POST", body: JSON.stringify({ status }) });
      loadRequests();
    } catch (e) { toast((e as Error).message, "err"); }
  }

  const publicUrl = (d: DocOverview) => (typeof window !== "undefined" ? window.location.origin : "") + d.public_path;

  return (
    <>
      <div className="usage-note">
        Páginas públicas sin login: <code className="mono">/privacidad</code>, <code className="mono">/terminos</code> y <code className="mono">/eliminacion-de-datos</code>.
        Solo se muestra la <b>versión publicada</b>; los borradores son privados. El contenido es texto/Markdown (sin HTML). Las URL exactas se registran en la app de Meta solo después de publicar y verificar.
      </div>

      <div className="cards" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(300px, 1fr))", marginBottom: 16 }}>
        {overview.map(d => (
          <div key={`${d.slug}-${d.lang}`} className={"card" + (d.slug === slug && d.lang === lang ? "" : "")} style={{ cursor: "pointer", outline: d.slug === slug && d.lang === lang ? "2px solid var(--brand)" : "none" }}
            onClick={() => selectDoc(d.slug, d.lang as "es" | "pt")}>
            <div className="card-head" style={{ marginBottom: 6 }}>
              <h3 style={{ fontSize: 15 }}>{SLUG_LABEL[d.slug]} <span className="tag">{d.lang.toUpperCase()}</span></h3>
              {d.published_version ? <span className="tag ok">Publicado v{d.published_version}</span> : <span className="tag warn">Sin publicar</span>}
            </div>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {d.draft_version ? `Borrador v${d.draft_version} pendiente · ` : ""}
              <a href={d.public_path} target="_blank" rel="noopener noreferrer" style={{ color: "var(--brand)" }}>{publicUrl(d)}</a>
            </div>
          </div>
        ))}
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div className="card-head" style={{ alignItems: "center" }}>
          <div>
            <h3>{SLUG_LABEL[slug]} · {lang.toUpperCase()}</h3>
            <div className="muted" style={{ fontSize: 12.5 }}>
              {latest ? `Última versión v${latest.version} (${latest.status}) · ${latest.author || "—"} · ${latest.created_at.slice(0, 16).replace("T", " ")}` : "Sin versiones todavía"}
              {published ? ` · pública v${published.version}` : ""}
            </div>
          </div>
          {canEdit && (
            <div style={{ display: "flex", gap: 6 }}>
              <button className="btn btn-ghost btn-sm" onClick={saveDraft} disabled={busy || loadingDoc || !!docError || !dirty || !title.trim() || !body.trim()}><Icon name="note" size={14} /> Guardar borrador</button>
              <button className="btn btn-sm" onClick={publish} disabled={busy || loadingDoc || !!docError || !latest || latest.status !== "draft" || dirty} title={dirty ? "Guarda el borrador antes de publicar" : "Publica la versión guardada"}>
                <Icon name="check" size={14} /> Publicar v{latest?.status === "draft" ? latest.version : "—"}
              </button>
            </div>
          )}
        </div>
        {loadingDoc && <p role="status">Cargando documento…</p>}
        {docError && <p role="alert">{docError} <button className="btn btn-sm" onClick={loadDoc}>Reintentar</button></p>}
        <label className="fld" style={{ marginBottom: 10 }}>Título
          <input value={title} onChange={e => { setTitle(e.target.value); setEdited(true); }} disabled={!canEdit || busy || loadingDoc || !!docError} maxLength={200} />
        </label>
        <div className="md-editor">
          <label className="fld">Contenido (Markdown)
            <textarea value={body} onChange={e => { setBody(e.target.value); setEdited(true); }} disabled={!canEdit || busy || loadingDoc || !!docError} spellCheck={false} />
          </label>
          <div>
            <div className="fld" style={{ marginBottom: 5 }}>Vista previa</div>
            <div className="md-preview"><Markdown text={body} /></div>
          </div>
        </div>
        {history.length > 0 && (
          <details style={{ marginTop: 12 }}>
            <summary className="muted" style={{ cursor: "pointer", fontSize: 13 }}>Historial ({history.length})</summary>
            <table style={{ marginTop: 8 }}><thead><tr><th>Versión</th><th>Estado</th><th>Autor</th><th>Creada</th><th>Publicada</th></tr></thead>
              <tbody>{history.map(h => (
                <tr key={h.id}><td className="mono">v{h.version}</td><td><span className={"tag " + (h.status === "published" ? "ok" : h.status === "draft" ? "warn" : "closed")}>{h.status}</span></td>
                  <td>{h.author || "—"}</td><td className="mono" style={{ fontSize: 11.5 }}>{h.created_at.slice(0, 16).replace("T", " ")}</td>
                  <td className="mono" style={{ fontSize: 11.5 }}>{h.published_at ? `${h.published_at.slice(0, 16).replace("T", " ")} · ${h.published_by || ""}` : "—"}</td></tr>
              ))}</tbody></table>
          </details>
        )}
      </div>

      {canEdit && (
        <>
          <h3 className="sec-title">Solicitudes de eliminación de datos</h3>
          <p className="muted" style={{ fontSize: 12.5, marginTop: -6 }}>Llegan desde la página pública. Verifica la identidad antes de eliminar; nada se borra automáticamente.</p>
          <table><thead><tr><th>#</th><th>Contacto</th><th>Canal</th><th>Detalle</th><th>Recibida</th><th>Estado</th><th>Acción</th></tr></thead>
            <tbody>{requests.length ? requests.map(r => (
              <tr key={r.id}><td className="mono">{r.id}</td><td>{r.contact}</td><td>{r.channel || "—"}</td><td style={{ fontSize: 12.5, maxWidth: 260 }}>{r.detail || "—"}</td>
                <td className="mono" style={{ fontSize: 11.5 }}>{r.created_at.slice(0, 16).replace("T", " ")}</td>
                <td><span className={"tag " + (DEL_STATUS[r.status]?.cls || "")}>{DEL_STATUS[r.status]?.label || r.status}</span></td>
                <td>
                  <select value={r.status} onChange={e => setReqStatus(r.id, e.target.value)} aria-label="Cambiar estado">
                    {Object.entries(DEL_STATUS).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
                  </select>
                </td></tr>
            )) : <tr><td colSpan={7} className="empty">Sin solicitudes.</td></tr>}</tbody></table>
        </>
      )}
    </>
  );
}

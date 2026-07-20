"use client";
import { useEffect, useRef, useState } from "react";
import { api, apiBlob, Conversation, Message, MediaRef } from "@/lib/api";
import TenantSelect from "@/components/TenantSelect";
import Icon from "@/components/Icon";

const CHAN: Record<string, { icon: string; label: string }> = {
  telegram: { icon: "telegram", label: "Telegram" },
  whatsapp: { icon: "whatsapp", label: "WhatsApp" },
  webchat: { icon: "webchat", label: "Webchat" },
};

function MediaBubble({ tenant, media }: { tenant: string; media: MediaRef }) {
  const [url, setUrl] = useState("");
  const [err, setErr] = useState(false);
  useEffect(() => {
    let alive = true; let obj = "";
    apiBlob(`/api/${tenant}/media?provider=${encodeURIComponent(media.provider)}&ref=${encodeURIComponent(media.ref)}`)
      .then(b => { if (alive) { obj = URL.createObjectURL(b); setUrl(obj); } })
      .catch(() => { if (alive) setErr(true); });
    return () => { alive = false; if (obj) URL.revokeObjectURL(obj); };
  }, [tenant, media.provider, media.ref]);
  const isImg = media.kind === "image" || media.kind === "sticker" || (media.mime || "").startsWith("image/");
  if (err) return <span className="muted" style={{ fontSize: 12 }}>No se pudo cargar el adjunto</span>;
  if (!url) return <span className="muted" style={{ fontSize: 12 }}>cargando adjunto…</span>;
  if (isImg) return <img src={url} alt={media.name || "imagen"} style={{ maxWidth: 240, maxHeight: 240, borderRadius: 8, display: "block" }} />;
  return <a href={url} download={media.name || "archivo"} className="tag" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="paperclip" size={13} /> {media.name || media.kind} · descargar</a>;
}

export default function Conversaciones() {
  const [tenant, setTenant] = useState("");
  const [convs, setConvs] = useState<Conversation[]>([]);
  const [sel, setSel] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<Message[]>([]);
  const [lead, setLead] = useState<Record<string, unknown>>({});
  const [reply, setReply] = useState("");
  const [imgUrl, setImgUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  function loadConvs() {
    if (!tenant) return;
    api<{ conversations: Conversation[] }>(`/api/${tenant}/conversations`).then(d => setConvs(d.conversations)).catch(() => setConvs([]));
  }
  useEffect(() => { setSel(null); setMsgs([]); setLead({}); if (tenant) loadConvs(); }, [tenant]);

  function open(id: string) {
    setSel(id);
    api<{ messages: Message[]; lead?: Record<string, unknown> }>(`/api/${tenant}/conversations/${id}`)
      .then(d => { setMsgs(d.messages); setLead(d.lead || {}); })
      .catch(() => { setMsgs([]); setLead({}); });
  }

  // Auto-refresco (tiempo real): sin esto había que recargar para ver mensajes nuevos.
  // Refresca la lista y el hilo abierto cada 4s. Se pausa si la pestaña no está visible.
  useEffect(() => {
    if (!tenant) return;
    const tick = () => {
      if (typeof document !== "undefined" && document.hidden) return;
      loadConvs();
      if (sel) {
        api<{ messages: Message[]; lead?: Record<string, unknown> }>(`/api/${tenant}/conversations/${sel}`)
          .then(d => { setMsgs(prev => (prev.length === d.messages.length ? prev : d.messages)); setLead(d.lead || {}); })
          .catch(() => {});
      }
    };
    const t = setInterval(tick, 4000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tenant, sel]);

  // Etiquetas legibles para los datos del lead (Fase 3).
  const LEAD_LABELS: Record<string, string> = {
    idioma: "Idioma", canal: "Canal", ruta: "Ruta", modo: "Modo",
    monto_enviar: "Monto a enviar", monto_recibir: "Monto a recibir", tasa: "Tasa",
    estado_tc: "Estado TC", aplica_promo: "Promo", tipo_cliente: "Tipo cliente",
    nombre: "Nombre", documento: "Documento", banco_pix: "Banco/PIX", beneficiario: "Beneficiario",
  };
  const leadEntries = Object.entries(lead).filter(
    ([k, v]) => LEAD_LABELS[k] && v !== null && v !== "" && v !== undefined,
  );

  const selConv = convs.find(c => c.id === sel) || null;

  async function send() {
    if (!sel || !reply.trim()) return;
    setBusy(true);
    try {
      await api(`/api/${tenant}/conversations/${sel}/reply`, { method: "POST", body: JSON.stringify({ text: reply.trim() }) });
      setReply("");
      open(sel); loadConvs();
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  }
  async function setStatus(status: string) {
    if (!sel) return;
    setBusy(true);
    try {
      await api(`/api/${tenant}/conversations/${sel}/status`, { method: "POST", body: JSON.stringify({ status }) });
      open(sel); loadConvs();
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  }
  async function sendImage() {
    if (!sel || !imgUrl.trim()) return;
    setBusy(true);
    try {
      await api(`/api/${tenant}/conversations/${sel}/send-image`, {
        method: "POST",
        body: JSON.stringify({ image_url: imgUrl.trim(), caption: reply.trim() || undefined }),
      });
      setImgUrl(""); setReply("");
      open(sel); loadConvs();
    } catch (e) { alert((e as Error).message); }
    setBusy(false);
  }
  // Sube varios archivos secuencialmente; el texto del asesor es el pie de foto del primero.
  async function uploadFiles(files: FileList | null) {
    if (!sel || !files || !files.length) return;
    setBusy(true);
    const arr = Array.from(files);
    const failures: string[] = [];
    try {
      for (let i = 0; i < arr.length; i++) {
        const fd = new FormData();
        fd.append("file", arr[i]);
        if (i === 0 && reply.trim()) fd.append("caption", reply.trim());
        try {
          const r = await api<{ delivery?: { sent?: boolean; detail?: string; channel?: string } }>(
            `/api/${tenant}/conversations/${sel}/upload`, { method: "POST", body: fd });
          if (r.delivery && r.delivery.sent === false) failures.push(`${arr[i].name}: ${r.delivery.detail || "no enviado"}`);
        } catch (e) { failures.push(`${arr[i].name}: ${(e as Error).message}`); }
      }
      setReply("");
      if (failures.length) alert(`Enviados ${arr.length - failures.length}/${arr.length}. No se enviaron:\n` + failures.join("\n"));
      open(sel); loadConvs();
    } finally { setBusy(false); }
  }

  const ch = (c: Conversation) => CHAN[c.channel] || { icon: "webchat", label: c.channel };
  const ChanTag = ({ c }: { c: Conversation }) => (
    <span className="tag" title={"Canal: " + ch(c).label} style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      <Icon name={ch(c).icon} size={12} /> {ch(c).label}
    </span>
  );

  return (
    <>
      <div className="row"><label className="muted">Cliente:</label><TenantSelect value={tenant} onChange={setTenant} /></div>
      <div className="grid2">
        <div className="list">
          {convs.length ? convs.map(c => (
            <div key={c.id} className={"citem" + (sel === c.id ? " on" : "")} onClick={() => open(c.id)}>
              <div style={{ display: "flex", justifyContent: "space-between", gap: 6, alignItems: "center" }}>
                <b style={{ fontSize: 12 }}>{c.user_ref}</b>
                <span style={{ display: "flex", gap: 4, flexShrink: 0 }}>
                  <ChanTag c={c} />
                  <span className={"tag" + (c.status === "handoff" ? " handoff" : "")}>{c.status}</span>
                </span>
              </div>
              <div className="prev">{c.last_message}</div>
              <div className="cid" style={{ display: "flex", alignItems: "center", gap: 4 }}>
                <span>{c.id} · {c.message_count} msgs</span>
                {c.assigned_to && <><Icon name="headset" size={11} /><span>{c.assigned_to}</span></>}
              </div>
            </div>
          )) : <div className="empty">Sin conversaciones aún. Escríbele al bot (Telegram/WhatsApp) o usa el Chat de prueba.</div>}
        </div>

        <div className="thread" style={{ display: "flex", flexDirection: "column" }}>
          {selConv ? (
            <div style={{ display: "flex", gap: 8, alignItems: "center", padding: "8px 10px", borderBottom: "1px solid var(--line)", flexWrap: "wrap" }}>
              <b style={{ fontSize: 12 }}>{selConv.user_ref}</b>
              <ChanTag c={selConv} />
              <span className={"tag" + (selConv.status === "handoff" ? " handoff" : "")}>{selConv.status}</span>
              <span className="grow" />
              {selConv.status === "handoff"
                ? <button className="btn btn-ghost" onClick={() => setStatus("active")} disabled={busy}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="ai" size={14} /> Devolver al bot</button>
                : <button className="btn" onClick={() => setStatus("handoff")} disabled={busy}
                    style={{ display: "inline-flex", alignItems: "center", gap: 5 }}><Icon name="headset" size={14} /> Tomar (pausar bot)</button>}
            </div>
          ) : null}

          {selConv && leadEntries.length > 0 && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "6px 10px", borderBottom: "1px solid var(--line)", alignItems: "center" }}>
              <span className="muted" style={{ fontSize: 11, display: "inline-flex", alignItems: "center", gap: 4 }}>
                <Icon name="user" size={12} /> Datos del lead:
              </span>
              {leadEntries.map(([k, v]) => (
                <span key={k} className="tag" style={{ fontSize: 11 }}>
                  {LEAD_LABELS[k]}: <b>{typeof v === "boolean" ? (v ? "sí" : "no") : String(v)}</b>
                </span>
              ))}
            </div>
          )}

          <div className="msgs" style={{ flex: 1 }}>
            {sel ? msgs.map((m, i) => (
              <div key={i} className={"msg " + (m.role === "user" ? "user" : "assistant")}>
                {m.media ? <div style={{ marginBottom: m.content ? 4 : 0 }}><MediaBubble tenant={tenant} media={m.media} /></div> : null}
                {m.content}
                {m.created_at && <small>{m.created_at.replace("T", " ").slice(0, 16)}</small>}
              </div>
            )) : <div className="empty">Selecciona una conversación</div>}
          </div>

          {selConv && (
            <div style={{ borderTop: "1px solid var(--line)" }}>
              <div style={{ display: "flex", gap: 6, padding: "8px 10px 4px" }}>
                <input style={{ flex: 1 }} placeholder="Escribe como asesor (le llega al usuario por el bot)…"
                  value={reply} onChange={e => setReply(e.target.value)}
                  onKeyDown={e => { if (e.key === "Enter") send(); }} disabled={busy} />
                <button className="btn" onClick={send} disabled={busy || !reply.trim()}>Enviar</button>
              </div>
              <div style={{ display: "flex", gap: 6, padding: "0 10px 8px", alignItems: "center" }}>
                <input ref={fileRef} type="file" multiple accept="image/*,application/pdf" style={{ display: "none" }}
                  onChange={e => { uploadFiles(e.target.files); if (fileRef.current) fileRef.current.value = ""; }} />
                <button className="btn" onClick={() => fileRef.current?.click()} disabled={busy}
                  style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                  <Icon name="paperclip" size={14} /> Adjuntar archivos
                </button>
                <span className="muted" style={{ fontSize: 11 }}>imágenes/PDF (varios) · o URL:</span>
                <input style={{ flex: 1, minWidth: 80 }} placeholder="https://…"
                  value={imgUrl} onChange={e => setImgUrl(e.target.value)} disabled={busy} />
                <button className="btn btn-ghost" onClick={sendImage} disabled={busy || !imgUrl.trim()}
                  style={{ display: "inline-flex", alignItems: "center" }} title="Enviar imagen por URL">
                  <Icon name="image" size={16} />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      {selConv?.status === "handoff" && (
        <p className="muted" style={{ fontSize: 12, marginTop: 8 }}>
          Bot en pausa: esta conversación la atiendes tú. Tus mensajes le llegan al usuario por {ch(selConv).label}. Cuando termines, pulsa &quot;Devolver al bot&quot;.
        </p>
      )}
    </>
  );
}

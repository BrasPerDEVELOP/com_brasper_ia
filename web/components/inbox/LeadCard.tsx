"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Advisor, Conversation, HandoffSummary, Note } from "@/lib/api";
import { chanOf, displayName, formatRef, LEAD_LABELS, leadStr, relTime, shortEmail, statusLabel, type Lead } from "@/lib/format";
import Icon from "../Icon";
import { Avatar } from "./ConversationItem";

const ORDER = ["ruta", "modo", "monto_enviar", "monto_recibir", "tasa", "estado_tc", "aplica_promo"];
const IDENTITY = ["nombre", "documento", "tipo_cliente", "idioma", "banco_pix", "beneficiario"];
const SUGGESTED_TAGS = ["primer envío", "monto alto", "reclamo", "comprobante", "vip", "seguimiento"];

type Delivery = { id: string; channel: string; state: string; detail: string | null; created_at: string };
const DELIVERY_TAG: Record<string, string> = { uncertain: "Incierto", failed: "Fallido", cancelled: "Cancelado" };
const DELIVERY_LABEL: Record<string, string> = {
  uncertain: "El canal pudo haberlo entregado; revisar antes de reenviar",
  failed: "Rechazado por el canal", cancelled: "Intervino un humano antes del envío",
};

/** Salidas automáticas que no se confirmaron: el asesor decide; nunca se reintentan solas. */
function DeliveryIssues({ conversationId }: { conversationId: string }) {
  const [items, setItems] = useState<Delivery[]>([]);
  useEffect(() => {
    let alive = true;
    api<{ deliveries: Delivery[] }>(`/api/conversations/${conversationId}/deliveries`)
      .then(d => { if (alive) setItems(d.deliveries.filter(x => x.state in DELIVERY_LABEL)); })
      .catch(() => { if (alive) setItems([]); });
    return () => { alive = false; };
  }, [conversationId]);
  if (!items.length) return null;
  return (
    <div className="psec">
      <h4><Icon name="clock" /> Envíos del bot sin confirmar</h4>
      <ul>{items.slice(0, 5).map(d => <li key={d.id}><span className={`tag ${d.state === "cancelled" ? "" : "warn"}`}>{DELIVERY_TAG[d.state]}</span> {DELIVERY_LABEL[d.state]} · {relTime(d.created_at)}</li>)}</ul>
    </div>
  );
}

export default function LeadCard({ c, lead, notes, tags, advisors, load, canAssign, canDelete, busy, onClose, onAssign, onDelete, onAddTag, onRemoveTag }: {
  c: Conversation; lead: Lead; notes: Note[]; tags: string[]; advisors: Advisor[]; load: Record<string, number>;
  canAssign: boolean; canDelete: boolean; busy: boolean;
  onClose: () => void; onAssign: (email: string | null) => void; onDelete: () => void;
  onAddTag: (tag: string) => void; onRemoveTag: (tag: string) => void;
}) {
  const [confirmDel, setConfirmDel] = useState(false);
  const [newTag, setNewTag] = useState("");
  const name = displayName(c, lead);
  const st = statusLabel(c);
  const has = (k: string) => lead[k] !== undefined && lead[k] !== null && lead[k] !== "";
  const quoteKeys = ORDER.filter(has);
  const idKeys = IDENTITY.filter(has);
  const promo = lead.aplica_promo === true || ["sí", "si", "true"].includes(String(lead.aplica_promo).toLowerCase());
  const handoff = (lead.handoff && typeof lead.handoff === "object" ? lead.handoff : null) as HandoffSummary | null;
  const proofPending = lead.commercial_stage === "proof_received" && lead.proof_validated !== true;
  const humanSource = typeof lead.last_human_source === "string" ? lead.last_human_source : null;
  const profileName = typeof lead.wa_profile_name === "string" ? lead.wa_profile_name : null;

  function addTag(t: string) { const v = t.trim().toLowerCase(); if (v && !tags.includes(v)) onAddTag(v); setNewTag(""); }

  return (
    <aside className="profile" aria-label="Ficha del cliente">
      <button className="ibtn profile-close" onClick={onClose} aria-label="Cerrar ficha"><Icon name="x" /></button>
      <div className="profile-hd">
        <Avatar name={name} seed={c.user_ref} channel={c.channel} />
        <b>{name}</b>
        <small>{formatRef(c.user_ref)} · {chanOf(c).label}{c.connection_id && c.connection_id !== "default" ? ` · ${c.connection_id}` : ""}</small>
        <div className="tagrow" style={{ justifyContent: "center" }}>
          <span className={`tag ${st.cls}`}>{st.text}</span>
          {humanSource === "whatsapp-app" && <span className="tag coex" title="Un humano respondió desde la app WhatsApp Business del celular">📱 celular</span>}
          {proofPending && <span className="tag warn" title="El comprobante recibido NO es un pago confirmado">Comprobante sin validar</span>}
        </div>
        {profileName && profileName !== name && <small title="Nombre de perfil de WhatsApp (no es identidad verificada)">Perfil WA: {profileName}</small>}
      </div>

      <DeliveryIssues conversationId={c.id} />

      {handoff && c.status === "handoff" && (
        <div className="psec">
          <h4><Icon name="headset" /> Derivación · {relTime(handoff.at)}</h4>
          <div className="handoff-box">
            <b>{handoff.reason_label}{handoff.extra ? ` — ${handoff.extra}` : ""}</b>
            {handoff.verified?.length > 0 && <div><span className="muted">Verificado:</span> {handoff.verified.join("; ")}</div>}
            {handoff.steps?.length > 0 && <div><span className="muted">Hecho:</span> {handoff.steps.join("; ")}</div>}
            <div><span className="muted">Pendiente:</span> {handoff.pending}</div>
          </div>
        </div>
      )}

      {quoteKeys.length > 0 && (
        <div className="psec">
          <h4><Icon name="coins" /> Operación</h4>
          {has("monto_enviar") && (
            <div className="quote-box">
              <span className="muted" style={{ fontSize: 12 }}>{has("ruta") ? leadStr(lead.ruta) : "Cotización"}</span>
              <span className="big">{leadStr(lead.monto_enviar)}{has("monto_recibir") ? ` → ${leadStr(lead.monto_recibir)}` : ""}</span>
              {has("tasa") && <span style={{ fontSize: 12.5 }}>Tasa {leadStr(lead.tasa)}</span>}
              {promo && <span className="promo"><span className="tag promo">Promo</span> aplica promoción Brasper</span>}
            </div>
          )}
          {quoteKeys.filter(k => !["monto_enviar", "monto_recibir", "tasa", "aplica_promo", "ruta"].includes(k) || !has("monto_enviar")).map(k => (
            <div className="kv" key={k}><span>{LEAD_LABELS[k]}</span><b>{leadStr(lead[k])}</b></div>
          ))}
        </div>
      )}

      {idKeys.length > 0 && (
        <div className="psec">
          <h4><Icon name="user" /> Cliente</h4>
          {idKeys.map(k => <div className="kv" key={k}><span>{LEAD_LABELS[k]}</span><b>{leadStr(lead[k])}</b></div>)}
        </div>
      )}

      <div className="psec">
        <h4><Icon name="tag" /> Etiquetas</h4>
        <div className="tagrow" style={{ marginBottom: 6 }}>
          {tags.map(t => (
            <span key={t} className="tag user-tag">{t}<button onClick={() => onRemoveTag(t)} aria-label={`Quitar etiqueta ${t}`} disabled={busy}>×</button></span>
          ))}
          {!tags.length && <span className="muted" style={{ fontSize: 12 }}>Sin etiquetas.</span>}
        </div>
        <div style={{ display: "flex", gap: 6 }}>
          <input value={newTag} onChange={e => setNewTag(e.target.value)} placeholder="Nueva etiqueta" maxLength={40} style={{ flex: 1, minWidth: 0 }}
            onKeyDown={e => { if (e.key === "Enter") addTag(newTag); }} aria-label="Nueva etiqueta" />
          <button className="btn btn-soft btn-sm" onClick={() => addTag(newTag)} disabled={busy || !newTag.trim()}><Icon name="plus" size={14} /></button>
        </div>
        <div className="tagrow" style={{ marginTop: 6 }}>
          {SUGGESTED_TAGS.filter(t => !tags.includes(t)).slice(0, 4).map(t => (
            <button key={t} className="chip" onClick={() => addTag(t)} disabled={busy}>+ {t}</button>
          ))}
        </div>
      </div>

      <div className="psec">
        <h4><Icon name="headset" /> Atención</h4>
        {canAssign ? (
          <label className="fld" style={{ marginBottom: 8 }}>Asignado a
            <select value={c.assigned_to || ""} disabled={busy} onChange={e => onAssign(e.target.value || null)} aria-label="Asignar asesor">
              <option value="">Sin asignar (libre)</option>
              {advisors.map(a => (
                <option key={a.email} value={a.email}>
                  {a.name || shortEmail(a.email)} · {load[a.email] || 0} en curso{a.presence ? ` · ${a.presence.status === "available" ? "disponible" : a.presence.status === "busy" ? "ocupado" : "ausente"}` : ""}
                </option>
              ))}
              {c.assigned_to && !advisors.some(a => a.email === c.assigned_to) && <option value={c.assigned_to}>{shortEmail(c.assigned_to)}</option>}
            </select>
          </label>
        ) : (
          <div className="kv"><span>Asignado a</span><b>{c.assigned_to ? shortEmail(c.assigned_to) : "—"}</b></div>
        )}
        <div className="kv"><span>Mensajes</span><b>{c.message_count}</b></div>
        <div className="kv"><span>Última actividad</span><b>{relTime(c.updated_at)}</b></div>
        <div className="kv"><span>ID</span><b className="mono" style={{ fontSize: 11 }}>{c.id}</b></div>
      </div>

      <div className="psec">
        <h4><Icon name="note" /> Notas internas {notes.length > 0 && <span className="tag" style={{ marginLeft: "auto" }}>{notes.length}</span>}</h4>
        {notes.length ? notes.map(n => (
          <div className="note" key={n.id}>
            <div>{n.text}</div>
            <small>{n.author ? shortEmail(n.author) : "equipo"} · {relTime(n.created_at)}</small>
          </div>
        )) : <div className="muted" style={{ fontSize: 12.5 }}>Sin notas. Usa la pestaña “Nota interna” del compositor.</div>}
      </div>

      {!quoteKeys.length && !idKeys.length && (
        <div className="psec muted" style={{ fontSize: 12.5 }}>
          Aún no hay datos del lead. Se completan solos cuando el bot cotiza o identifica al cliente.
        </div>
      )}

      {canDelete && (
        <div className="psec" style={{ marginTop: "auto" }}>
          {!confirmDel ? (
            <button className="btn btn-ghost btn-sm" style={{ color: "var(--danger)" }} onClick={() => setConfirmDel(true)} disabled={busy}>
              <Icon name="x" size={14} /> Eliminar conversación
            </button>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              <span className="muted" style={{ fontSize: 12.5 }}>Se borran todos los mensajes de <b>{formatRef(c.user_ref)}</b>. No se puede deshacer.</span>
              <div style={{ display: "flex", gap: 6 }}>
                <button className="btn btn-danger btn-sm" onClick={() => { setConfirmDel(false); onDelete(); }} disabled={busy}>Sí, eliminar</button>
                <button className="btn btn-ghost btn-sm" onClick={() => setConfirmDel(false)}>Cancelar</button>
              </div>
            </div>
          )}
        </div>
      )}
    </aside>
  );
}

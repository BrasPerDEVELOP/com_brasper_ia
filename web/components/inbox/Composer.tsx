"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { QuickReply } from "@/lib/api";
import { fmtBytes, type Lead } from "@/lib/format";
import Icon from "../Icon";
import type { PendingFile } from "./types";

export const MAX_FILE_BYTES = 10 * 1024 * 1024; // igual que _MAX_UPLOAD_BYTES del backend
export const WA_IMG_BYTES = 5 * 1024 * 1024;    // WhatsApp exige imagen <= 5 MB

const EMOJIS = ["😊", "🙌", "👍", "🙏", "✅", "✨", "💙", "🎉", "📎", "💱", "💸", "🏦", "📱", "⏳", "🔔", "❤️", "😉", "👋", "🤝", "📌", "🇵🇪", "🇧🇷", "⚠️", "❓"];

/** Valida un archivo según el canal; devuelve el mensaje de error o undefined. */
export function validateFile(f: File, channel: string): string | undefined {
  const img = f.type.startsWith("image/");
  const pdf = f.type === "application/pdf";
  if (!img && !pdf) return "Solo imágenes o PDF";
  if (f.size > MAX_FILE_BYTES) return "Supera 10 MB";
  if (channel === "whatsapp" && !img) return "WhatsApp solo acepta imágenes";
  if (channel === "whatsapp" && f.size > WA_IMG_BYTES) return "WhatsApp: imagen máx. 5 MB";
  return undefined;
}

/** Rellena {nombre}, {monto}, {monto_recibir}, {ruta} con los datos del lead. */
export function fillTemplate(text: string, lead: Lead, fallbackName: string): string {
  const v: Record<string, string> = {
    nombre: (typeof lead.nombre === "string" && lead.nombre.trim()) || fallbackName || "",
    monto: lead.monto_enviar != null ? String(lead.monto_enviar) : "",
    monto_recibir: lead.monto_recibir != null ? String(lead.monto_recibir) : "",
    ruta: lead.ruta != null ? String(lead.ruta) : "",
  };
  return text.replace(/\{(\w+)\}/g, (_, k: string) => v[k] ?? `{${k}}`).replace(/ {2,}/g, " ").replace(/ ([,.!?])/g, "$1");
}

export type ComposerMode = "message" | "note";

export default function Composer({ channel, botPaused, busy, progress, pending, onAddFiles, onRemoveFile, onSend, onSendUrl, onSendNote,
  quickReplies, lead, leadName, disabled, dragging }: {
  channel: string; botPaused: boolean; busy: boolean; progress?: { done: number; total: number } | null;
  pending: PendingFile[]; onAddFiles: (files: FileList | File[]) => void; onRemoveFile: (id: string) => void;
  onSend: (text: string) => Promise<boolean>; onSendUrl: (url: string, caption: string) => Promise<boolean>;
  onSendNote: (text: string) => Promise<boolean>;
  quickReplies: QuickReply[]; lead: Lead; leadName: string;
  disabled?: boolean; dragging?: boolean;
}) {
  const [text, setText] = useState("");
  const [mode, setMode] = useState<ComposerMode>("message");
  const [menu, setMenu] = useState<"attach" | "quick" | "emoji" | null>(null);
  const [qrFilter, setQrFilter] = useState("");
  const [urlMode, setUrlMode] = useState(false);
  const [url, setUrl] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);

  // Textarea autoexpandible (1–6 líneas).
  useEffect(() => {
    const ta = taRef.current; if (!ta) return;
    ta.style.height = "0px";
    ta.style.height = Math.min(160, Math.max(40, ta.scrollHeight)) + "px";
  }, [text]);

  // Cerrar menús al hacer clic fuera.
  useEffect(() => {
    if (!menu) return;
    const h = (e: MouseEvent) => { if (!wrapRef.current?.contains(e.target as Node)) setMenu(null); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, [menu]);

  const filteredQr = useMemo(() => {
    const f = qrFilter.trim().toLowerCase();
    return quickReplies.filter(q => !f || q.title.toLowerCase().includes(f) || q.text.toLowerCase().includes(f));
  }, [quickReplies, qrFilter]);

  const isNote = mode === "note";
  const canSend = !busy && !disabled && (text.trim().length > 0 || (!isNote && pending.some(p => !p.error)));

  async function submit() {
    if (!canSend) return;
    if (isNote) { if (await onSendNote(text.trim())) { setText(""); taRef.current?.focus(); } return; }
    if (urlMode && url.trim()) {
      if (await onSendUrl(url.trim(), text.trim())) { setUrl(""); setUrlMode(false); setText(""); }
      return;
    }
    if (await onSend(text.trim())) { setText(""); taRef.current?.focus(); }
  }

  function onKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
    if (e.key === "/" && !text && quickReplies.length) { e.preventDefault(); setMenu("quick"); }
  }

  function onPaste(e: React.ClipboardEvent) {
    if (isNote) return;
    const files = Array.from(e.clipboardData.files || []);
    if (files.length) { e.preventDefault(); onAddFiles(files); }
  }

  function useQuick(q: QuickReply) {
    setText(fillTemplate(q.text, lead, leadName));
    setMenu(null); setQrFilter("");
    setTimeout(() => taRef.current?.focus(), 0);
  }

  function insertEmoji(emoji: string) {
    const ta = taRef.current;
    const start = ta?.selectionStart ?? text.length;
    const end = ta?.selectionEnd ?? text.length;
    const next = text.slice(0, start) + emoji + text.slice(end);
    setText(next);
    setMenu(null);
    setTimeout(() => { if (ta) { ta.focus(); ta.selectionStart = ta.selectionEnd = start + emoji.length; } }, 0);
  }

  const placeholder = disabled ? "Conversación cerrada: reábrela para escribir"
    : isNote ? "Nota interna (solo la ve el equipo)…"
    : pending.length ? "Pie de foto (opcional)…"
    : botPaused ? "Escribe al cliente…"
    : "Escribe para tomar la conversación y pausar el bot…";

  return (
    <div className={"composer" + (dragging ? " drag" : "") + (isNote ? " note" : "")} ref={wrapRef}>
      <div className="compose-tabs" role="tablist" aria-label="Modo">
        <button role="tab" aria-selected={!isNote} className={"ctab" + (!isNote ? " on" : "")} onClick={() => setMode("message")}>
          <Icon name="send" size={13} /> Mensaje
        </button>
        <button role="tab" aria-selected={isNote} className={"ctab" + (isNote ? " on" : "")} onClick={() => setMode("note")}>
          <Icon name="note" size={13} /> Nota interna
        </button>
        {isNote && <span className="muted" style={{ fontSize: 11.5, marginLeft: 6 }}>No se envía al cliente.</span>}
      </div>

      {!isNote && pending.length > 0 && (
        <div className="attach-row" aria-label="Adjuntos por enviar">
          {pending.map(p => (
            <div key={p.id} className={"attach" + (p.error ? " err" : "")} title={p.error ? `${p.file.name}: ${p.error}` : p.file.name}>
              {p.preview ? <img src={p.preview} alt="" /> : <span><Icon name={p.file.type.includes("pdf") ? "pdf" : "file"} size={22} /><br />{p.file.name.slice(0, 14)}</span>}
              <span className="sz">{p.error ? p.error : fmtBytes(p.file.size)}</span>
              <button className="rm" onClick={() => onRemoveFile(p.id)} aria-label="Quitar adjunto" disabled={busy}><Icon name="x" size={12} /></button>
            </div>
          ))}
        </div>
      )}
      {progress && progress.total > 0 && (
        <div>
          <div className="muted" style={{ fontSize: 11.5, marginBottom: 3 }}>Enviando {Math.min(progress.done + 1, progress.total)} de {progress.total}…</div>
          <div className="progress"><i style={{ width: `${(progress.done / progress.total) * 100}%` }} /></div>
        </div>
      )}
      {urlMode && !isNote && (
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <Icon name="link" size={15} className="muted" />
          <input style={{ flex: 1 }} placeholder="https://… (imagen pública)" value={url} onChange={e => setUrl(e.target.value)} autoFocus
            onKeyDown={e => { if (e.key === "Enter") submit(); if (e.key === "Escape") setUrlMode(false); }} />
          <button className="ibtn" onClick={() => { setUrlMode(false); setUrl(""); }} aria-label="Cancelar URL"><Icon name="x" size={16} /></button>
        </div>
      )}

      <div className="compose-main">
        {!isNote && (
          <div className="rel">
            <button className={"ibtn" + (menu === "attach" ? " on" : "")} onClick={() => setMenu(m => (m === "attach" ? null : "attach"))}
              disabled={disabled || busy} aria-label="Adjuntar" title="Adjuntar">
              <Icon name="paperclip" size={19} />
            </button>
            {menu === "attach" && (
              <div className="pop" role="menu">
                <button className="item" role="menuitem" onClick={() => { setMenu(null); fileRef.current?.click(); }}>
                  <Icon name="image" /> Imagen o PDF desde el equipo
                </button>
                <button className="item" role="menuitem" onClick={() => { setMenu(null); setUrlMode(true); }}>
                  <Icon name="link" /> Imagen por URL pública
                </button>
                <div className="sep" />
                <div className="muted" style={{ fontSize: 11.5, padding: "2px 10px 6px" }}>
                  También puedes arrastrar archivos al chat o pegar una imagen (Ctrl V).<br />
                  {channel === "whatsapp" ? "WhatsApp: solo imágenes, máx. 5 MB." : "Máx. 10 MB por archivo."}
                </div>
              </div>
            )}
            <input ref={fileRef} type="file" multiple accept="image/*,application/pdf" style={{ display: "none" }}
              onChange={e => { if (e.target.files) onAddFiles(e.target.files); e.target.value = ""; }} />
          </div>
        )}
        {!isNote && quickReplies.length > 0 && (
          <div className="rel">
            <button className={"ibtn" + (menu === "quick" ? " on" : "")} onClick={() => setMenu(m => (m === "quick" ? null : "quick"))}
              disabled={disabled || busy} aria-label="Respuestas rápidas" title="Respuestas rápidas (/)">
              <Icon name="zap" size={19} />
            </button>
            {menu === "quick" && (
              <div className="pop qr" role="menu">
                <input autoFocus placeholder="Buscar respuesta…" value={qrFilter} onChange={e => setQrFilter(e.target.value)}
                  onKeyDown={e => { if (e.key === "Escape") setMenu(null); if (e.key === "Enter" && filteredQr[0]) useQuick(filteredQr[0]); }} />
                <div className="qr-list">
                  {filteredQr.map(q => (
                    <button key={q.key} className="item qr-item" role="menuitem" onClick={() => useQuick(q)}>
                      <span className="qr-t">{q.title} <span className="tag" style={{ fontSize: 10 }}>{q.lang}</span></span>
                      <span className="qr-p">{fillTemplate(q.text, lead, leadName)}</span>
                    </button>
                  ))}
                  {!filteredQr.length && <div className="muted" style={{ padding: 10, fontSize: 12.5 }}>Sin coincidencias.</div>}
                </div>
              </div>
            )}
          </div>
        )}
        <div className="rel">
          <button className={"ibtn" + (menu === "emoji" ? " on" : "")} onClick={() => setMenu(m => (m === "emoji" ? null : "emoji"))}
            disabled={disabled || busy} aria-label="Emojis" title="Emojis">
            <span aria-hidden="true" style={{ fontSize: 18, lineHeight: 1 }}>🙂</span>
          </button>
          {menu === "emoji" && (
            <div className="pop emoji-pop" role="menu" aria-label="Elegir emoji">
              {EMOJIS.map(e => <button key={e} role="menuitem" onClick={() => insertEmoji(e)} aria-label={`Insertar ${e}`}>{e}</button>)}
            </div>
          )}
        </div>
        <textarea ref={taRef} rows={1} value={text} placeholder={placeholder} disabled={disabled || busy}
          onChange={e => setText(e.target.value)} onKeyDown={onKey} onPaste={onPaste} aria-label={isNote ? "Nota interna" : "Mensaje"} />
        <button className={"btn" + (isNote ? " btn-soft" : "")} onClick={submit} disabled={!canSend || (urlMode && !isNote && !url.trim())}
          aria-label={isNote ? "Guardar nota" : "Enviar"} title={isNote ? "Guardar nota (Enter)" : "Enviar (Enter)"}>
          {busy ? <Icon name="loader" size={16} /> : <Icon name={isNote ? "note" : "send"} size={16} />}
        </button>
      </div>
      <div className="compose-foot">
        <span className={"botstate" + (botPaused ? " paused" : "")}>
          <span className="dot" />{botPaused ? "Bot en pausa · atiendes tú" : "Bot activo · responde solo"}
        </span>
        <span className="hint">Enter envía · Shift+Enter salto{quickReplies.length ? " · / respuestas rápidas" : ""}</span>
      </div>
    </div>
  );
}

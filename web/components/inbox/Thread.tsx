"use client";
import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Conversation, QuickReply } from "@/lib/api";
import { chanOf, dayKey, dayLabel, displayName, statusLabel, type Lead } from "@/lib/format";
import Icon from "../Icon";
import Composer from "./Composer";
import { Avatar } from "./ConversationItem";
import MessageBubble from "./MessageBubble";
import type { LocalMessage, PendingFile } from "./types";

const NEAR_BOTTOM = 96;
const WINDOW = 300; // mensajes renderizados por defecto en hilos largos

export default function Thread({ c, lead, msgs, loading, busy, progress, pending, notesCount, quickReplies, showProfile,
  onToggleProfile, onBack, onStatus, onAddFiles, onRemoveFile, onSend, onSendUrl, onSendNote, onOpenMedia }: {
  c: Conversation | null; lead: Lead; msgs: LocalMessage[]; loading: boolean; busy: boolean;
  progress: { done: number; total: number } | null; pending: PendingFile[]; notesCount: number; quickReplies: QuickReply[];
  showProfile: boolean; onToggleProfile: () => void; onBack: () => void;
  onStatus: (s: "handoff" | "active" | "closed") => void;
  onAddFiles: (f: FileList | File[]) => void; onRemoveFile: (id: string) => void;
  onSend: (t: string) => Promise<boolean>; onSendUrl: (u: string, cap: string) => Promise<boolean>;
  onSendNote: (t: string) => Promise<boolean>;
  onOpenMedia: (url: string, name?: string) => void;
}) {
  const boxRef = useRef<HTMLDivElement>(null);
  const [atBottom, setAtBottom] = useState(true);
  const [newCount, setNewCount] = useState(0);
  const [dragging, setDragging] = useState(false);
  const [showAll, setShowAll] = useState(false);
  const dragDepth = useRef(0);
  const lastLen = useRef(0);
  const lastConv = useRef<string | null>(null);

  const scrollToBottom = useCallback((smooth = false) => {
    const el = boxRef.current; if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? "smooth" : "auto" });
    setNewCount(0);
  }, []);

  // Al cambiar de conversación: ir al final sin animación. Al llegar mensajes: seguir abajo
  // solo si el asesor ya estaba abajo; si no, contar "nuevos" para el botón flotante.
  useLayoutEffect(() => {
    const changed = lastConv.current !== (c?.id ?? null);
    if (changed) { lastConv.current = c?.id ?? null; lastLen.current = msgs.length; setShowAll(false); scrollToBottom(false); return; }
    if (msgs.length > lastLen.current) {
      const added = msgs.length - lastLen.current;
      const lastMine = (msgs[msgs.length - 1]?.sender || msgs[msgs.length - 1]?.role) !== "user";
      if (atBottom || lastMine) scrollToBottom(true); else setNewCount(n => n + added);
    }
    lastLen.current = msgs.length;
  }, [msgs, c?.id, atBottom, scrollToBottom]);

  const onScroll = () => {
    const el = boxRef.current; if (!el) return;
    const near = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM;
    setAtBottom(near);
    if (near) setNewCount(0);
  };

  // Drag & drop sobre todo el hilo.
  const onDragEnter = (e: React.DragEvent) => { if (!c) return; e.preventDefault(); dragDepth.current++; setDragging(true); };
  const onDragLeave = (e: React.DragEvent) => { e.preventDefault(); if (--dragDepth.current <= 0) { dragDepth.current = 0; setDragging(false); } };
  const onDragOver = (e: React.DragEvent) => { e.preventDefault(); };
  const onDrop = (e: React.DragEvent) => {
    e.preventDefault(); dragDepth.current = 0; setDragging(false);
    if (c && e.dataTransfer.files?.length) onAddFiles(e.dataTransfer.files);
  };

  useEffect(() => { setNewCount(0); setAtBottom(true); }, [c?.id]);

  if (!c) {
    return (
      <section className="thread" aria-label="Conversación">
        <div className="empty" style={{ margin: "auto", maxWidth: 380 }}>
          <Icon name="inbox" size={40} className="faint" />
          <div style={{ marginTop: 10, fontWeight: 600, color: "var(--ink)" }}>Selecciona una conversación</div>
          <div style={{ fontSize: 13, lineHeight: 1.7 }}>
            <kbd className="kbd">↑</kbd> <kbd className="kbd">↓</kbd> moverse · <kbd className="kbd">T</kbd> tomar · <kbd className="kbd">R</kbd> devolver al bot · <kbd className="kbd">E</kbd> cerrar · <kbd className="kbd">Ctrl K</kbd> buscar
          </div>
        </div>
      </section>
    );
  }

  const name = displayName(c, lead);
  const st = statusLabel(c);
  const paused = c.status === "handoff";
  const hidden = !showAll && msgs.length > WINDOW ? msgs.length - WINDOW : 0;
  const shown = hidden ? msgs.slice(hidden) : msgs;
  let lastDay = "";
  let lastSender = "";

  return (
    <section className="thread" aria-label={`Conversación con ${name}`}
      onDragEnter={onDragEnter} onDragLeave={onDragLeave} onDragOver={onDragOver} onDrop={onDrop}>
      <header className="thread-hd">
        <button className="ibtn back" onClick={onBack} aria-label="Volver a la lista"><Icon name="arrowleft" /></button>
        <Avatar name={name} seed={c.user_ref} channel={c.channel} size="sm" />
        <div className="who">
          <b>{name}</b>
          <small>{chanOf(c).label} · <span className={`tag ${st.cls}`} style={{ padding: "0 6px" }}>{st.text}</span></small>
        </div>
        <div className="acts">
          {c.status === "handoff" ? (
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => onStatus("active")} disabled={busy} title="Devolver al bot (R)">
                <Icon name="bot" size={15} /><span className="lbl">Devolver al bot</span>
              </button>
              <button className="btn btn-ghost btn-sm" onClick={() => onStatus("closed")} disabled={busy} title="Cerrar conversación (E)">
                <Icon name="check" size={15} /><span className="lbl">Cerrar</span>
              </button>
            </>
          ) : c.status === "closed" ? (
            <button className="btn btn-soft btn-sm" onClick={() => onStatus("handoff")} disabled={busy} title="Reabrir y atender (T)">
              <Icon name="headset" size={15} /><span className="lbl">Reabrir</span>
            </button>
          ) : (
            <button className="btn btn-sm" onClick={() => onStatus("handoff")} disabled={busy} title="Tomar la conversación: pausa el bot (T)">
              <Icon name="headset" size={15} /><span className="lbl">Tomar</span>
            </button>
          )}
          <button className={"ibtn rel" + (showProfile ? " on" : "")} onClick={onToggleProfile} aria-label="Ficha del cliente" title="Ficha del cliente">
            <Icon name="info" />
            {notesCount > 0 && <span className="badge mini">{notesCount}</span>}
          </button>
        </div>
      </header>

      <div className="msgs" ref={boxRef} onScroll={onScroll} aria-live="polite">
        {loading && !msgs.length ? (
          <>
            <span className="sk" style={{ height: 44, width: "45%", alignSelf: "flex-start", borderRadius: 16 }} />
            <span className="sk" style={{ height: 60, width: "55%", alignSelf: "flex-end", borderRadius: 16, marginTop: 6 }} />
            <span className="sk" style={{ height: 44, width: "38%", alignSelf: "flex-start", borderRadius: 16, marginTop: 6 }} />
          </>
        ) : msgs.length ? (
          <>
            {hidden > 0 && (
              <button className="btn btn-ghost btn-sm" style={{ alignSelf: "center", marginBottom: 8 }} onClick={() => setShowAll(true)}>
                Cargar {hidden} mensajes anteriores
              </button>
            )}
            {shown.map((m, i) => {
              const dk = dayKey(m.created_at);
              const sep = dk && dk !== lastDay; if (dk) lastDay = dk;
              const sender = m.sender || (m.role === "user" ? "user" : "bot");
              const showFrom = sender !== "user" && (sender !== lastSender || !!sep);
              lastSender = sender;
              return (
                <Fragment key={m._local?.id || `${hidden + i}-${m.created_at || ""}`}>
                  {sep && <div className="daysep">{dayLabel(m.created_at)}</div>}
                  <MessageBubble m={m} showFrom={showFrom} onOpenMedia={onOpenMedia} />
                </Fragment>
              );
            })}
          </>
        ) : <div className="empty">Sin mensajes todavía.</div>}
      </div>

      {(newCount > 0 || !atBottom) && msgs.length > 0 && (
        <button className="jump" onClick={() => scrollToBottom(true)}>
          <Icon name="arrowdown" /> {newCount > 0 ? `${newCount} nuevo${newCount > 1 ? "s" : ""}` : "Ir al final"}
        </button>
      )}

      <Composer channel={c.channel} botPaused={paused} busy={busy} progress={progress} pending={pending}
        onAddFiles={onAddFiles} onRemoveFile={onRemoveFile} onSend={onSend} onSendUrl={onSendUrl} onSendNote={onSendNote}
        quickReplies={quickReplies} lead={lead} leadName={name}
        disabled={c.status === "closed"} dragging={dragging} />
    </section>
  );
}

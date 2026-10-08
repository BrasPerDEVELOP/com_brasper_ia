"use client";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Conversation } from "@/lib/api";
import Icon from "../Icon";
import ConversationItem from "./ConversationItem";
import type { InboxTab } from "./types";

const TABS: { key: InboxTab; label: string }[] = [
  { key: "inbox", label: "Entrada" },
  { key: "mine", label: "Míos" },
  { key: "queue", label: "Libres" },
  { key: "bot", label: "Bot" },
  { key: "closed", label: "Cerrados" },
];
const CHANNELS: { key: string; label: string }[] = [
  { key: "whatsapp", label: "WhatsApp" }, { key: "telegram", label: "Telegram" }, { key: "webchat", label: "Web" },
];

// Virtualización ligera (sin dependencias): a partir de VIRT_FROM ítems solo se
// renderizan los visibles + un margen. Los ítems tienen alto casi fijo (ROW_H).
const VIRT_FROM = 60;
const ROW_H = 92;
const OVERSCAN = 8;

export default function ConversationList({ convs, counts, tab, onTab, query, onQuery, sel, unread, loading, now, onOpen, searchRef,
  allTags, tagFilter, onTagFilter, channelFilter, onChannelFilter }: {
  convs: Conversation[]; counts: Record<InboxTab, number>; tab: InboxTab; onTab: (t: InboxTab) => void;
  query: string; onQuery: (q: string) => void; sel: string | null; unread: Record<string, number>;
  loading: boolean; now: number; onOpen: (id: string) => void; searchRef: React.RefObject<HTMLInputElement | null>;
  allTags: string[]; tagFilter: string | null; onTagFilter: (t: string | null) => void;
  channelFilter: string | null; onChannelFilter: (c: string | null) => void;
}) {
  const bodyRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ top: 0, h: 800 });
  const virt = convs.length > VIRT_FROM;

  useLayoutEffect(() => {
    const el = bodyRef.current; if (!el) return;
    const upd = () => setView({ top: el.scrollTop, h: el.clientHeight || 800 });
    upd();
    const ro = new ResizeObserver(upd);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Mantener visible el ítem seleccionado al navegar con teclado.
  useEffect(() => {
    if (!sel || !bodyRef.current) return;
    if (virt) {
      const i = convs.findIndex(c => c.id === sel);
      if (i < 0) return;
      const el = bodyRef.current;
      const top = i * ROW_H;
      if (top < el.scrollTop) el.scrollTop = top;
      else if (top + ROW_H > el.scrollTop + el.clientHeight) el.scrollTop = top + ROW_H - el.clientHeight;
      return;
    }
    const el = bodyRef.current.querySelector<HTMLElement>('[aria-selected="true"]');
    el?.scrollIntoView({ block: "nearest" });
  }, [sel, virt, convs]);

  let start = 0, end = convs.length;
  if (virt) {
    start = Math.max(0, Math.floor(view.top / ROW_H) - OVERSCAN);
    end = Math.min(convs.length, Math.ceil((view.top + view.h) / ROW_H) + OVERSCAN);
  }
  const slice = convs.slice(start, end);
  const hasFilters = allTags.length > 0 || true;

  return (
    <aside className="clist" aria-label="Conversaciones">
      <div className="clist-top">
        <div className="search">
          <Icon name="search" />
          <input ref={searchRef} value={query} onChange={e => onQuery(e.target.value)} placeholder="Buscar nombre, número o mensaje"
            aria-label="Buscar conversación" />
          {!query && <kbd>Ctrl K</kbd>}
        </div>
        {hasFilters && (
          <div className="chips" aria-label="Filtros">
            {CHANNELS.map(ch => (
              <button key={ch.key} className={"chip" + (channelFilter === ch.key ? " on" : "")}
                onClick={() => onChannelFilter(channelFilter === ch.key ? null : ch.key)}>{ch.label}</button>
            ))}
            {allTags.map(t => (
              <button key={t} className={"chip" + (tagFilter === t ? " on" : "")} onClick={() => onTagFilter(tagFilter === t ? null : t)}>#{t}</button>
            ))}
          </div>
        )}
        <div className="tabs" role="tablist">
          {TABS.map(t => (
            <button key={t.key} role="tab" aria-selected={tab === t.key} className={"tab" + (tab === t.key ? " on" : "")} onClick={() => onTab(t.key)}>
              {t.label}{counts[t.key] > 0 && <span className="n">{counts[t.key]}</span>}
            </button>
          ))}
        </div>
      </div>
      <div className="clist-body" ref={bodyRef} role="listbox" aria-label="Lista de conversaciones"
        onScroll={virt ? e => setView(v => ({ ...v, top: (e.target as HTMLDivElement).scrollTop })) : undefined}>
        {loading && !convs.length ? (
          Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="citem" style={{ cursor: "default" }}>
              <span className="sk" style={{ width: 40, height: 40, borderRadius: "50%" }} />
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                <span className="sk" style={{ height: 12, width: "55%" }} />
                <span className="sk" style={{ height: 11, width: "85%" }} />
                <span className="sk" style={{ height: 10, width: "35%" }} />
              </div>
            </div>
          ))
        ) : convs.length ? (
          <>
            {virt && start > 0 && <div style={{ height: start * ROW_H }} aria-hidden="true" />}
            {slice.map(c => (
              <div key={c.id} style={virt ? { height: ROW_H, overflow: "hidden" } : undefined}>
                <ConversationItem c={c} on={sel === c.id} unread={unread[c.id] || 0} now={now} onClick={() => onOpen(c.id)} />
              </div>
            ))}
            {virt && end < convs.length && <div style={{ height: (convs.length - end) * ROW_H }} aria-hidden="true" />}
          </>
        ) : (
          <div className="empty">
            {query || tagFilter || channelFilter ? "Sin resultados para ese filtro." : tab === "inbox"
              ? "Sin conversaciones aún. Escríbele al bot por Telegram o WhatsApp, o usa el Chat de prueba."
              : "Nada por aquí."}
          </div>
        )}
      </div>
    </aside>
  );
}

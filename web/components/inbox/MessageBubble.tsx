"use client";
import { clockTime, shortEmail } from "@/lib/format";
import Icon from "../Icon";
import MediaBubble from "./MediaBubble";
import type { LocalMessage } from "./types";

/** Burbuja del hilo. Tres voces: cliente (izquierda), bot (derecha, punteada) y asesor (derecha, azul). */
export default function MessageBubble({ m, showFrom, onOpenMedia }: {
  m: LocalMessage; showFrom?: boolean; onOpenMedia: (url: string, name?: string) => void;
}) {
  const sender = m.sender || (m.role === "user" ? "user" : "bot");
  const mine = sender !== "user";
  const st = m._local?.state;
  const cls = ["msg", sender === "user" ? "user" : sender === "agent" ? "agent" : "bot",
    st === "pending" ? "pending" : "", st === "failed" ? "failed" : ""].filter(Boolean).join(" ");
  return (
    <div className={cls}>
      {showFrom && mine && (
        <div className="from">
          <Icon name={sender === "agent" ? "headset" : "bot"} size={12} />
          {sender === "agent" ? (m.agent_email ? shortEmail(m.agent_email) : "Asesor") : "Bot Brasper"}
        </div>
      )}
      {m.media ? <div style={{ marginBottom: m.content ? 6 : 0 }}><MediaBubble media={m.media} onOpen={onOpenMedia} /></div> : null}
      {m.content}
      <small className="ts">
        {st === "pending" ? <><Icon name="clock" size={10} /> enviando…</> : clockTime(m.created_at)}
        {mine && !st ? <Icon name="check" size={10} /> : null}
      </small>
      {st === "failed" && (
        <div className="fail">
          <Icon name="alert" size={12} /> {m._local?.detail || "No se envió"}
          {m._local?.retry && <button onClick={m._local.retry}>Reintentar</button>}
        </div>
      )}
    </div>
  );
}

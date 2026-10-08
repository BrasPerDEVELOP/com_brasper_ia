"use client";
import type { Conversation } from "@/lib/api";
import { avatarColor, chanOf, displayName, initials, relTime, SLA_LATE_MIN, SLA_WARN_MIN, statusLabel, waitingMinutes } from "@/lib/format";
import Icon from "../Icon";

export function Avatar({ name, seed, channel, size }: { name: string; seed: string; channel?: string; size?: "sm" }) {
  const ch = channel ? chanOf({ channel }) : null;
  return (
    <span className={"avatar" + (size ? ` ${size}` : "")} style={{ background: avatarColor(seed) }} aria-hidden="true">
      {initials(name)}
      {ch && <span className={`ch ch-${channel}`}><Icon name={ch.icon} size={11} /></span>}
    </span>
  );
}

export default function ConversationItem({ c, on, unread, now, onClick }: {
  c: Conversation; on: boolean; unread: number; now: number; onClick: () => void;
}) {
  const name = displayName(c);
  const st = statusLabel(c);
  const wait = c.status === "handoff" ? waitingMinutes(c.updated_at, now) : 0;
  const tags = c.tags || [];
  return (
    <div className={"citem" + (on ? " on" : "") + (unread > 0 && !on ? " unread" : "")} onClick={onClick}
      role="option" aria-selected={on} tabIndex={-1}>
      <Avatar name={name} seed={c.user_ref} channel={c.channel} />
      <div style={{ minWidth: 0 }}>
        <div className="l1">
          <span className="name">{name}</span>
          <span className="time">{relTime(c.updated_at, now)}</span>
        </div>
        <div className="l2">
          <span className="prev">{c.last_message || "—"}</span>
          {unread > 0 && !on && <span className="badge">{unread > 99 ? "99+" : unread}</span>}
        </div>
        <div className="l3">
          <span className={`tag ${st.cls}`}>{st.text}</span>
          {wait >= SLA_WARN_MIN && (
            <span className={"sla" + (wait >= SLA_LATE_MIN ? " late" : "")} title="Minutos desde la última actividad">
              <Icon name="clock" size={11} /> {wait} min
            </span>
          )}
          {tags.slice(0, 2).map(t => <span key={t} className="tag user-tag">{t}</span>)}
          {tags.length > 2 && <span className="tag" title={tags.slice(2).join(", ")}>+{tags.length - 2}</span>}
          {c.connection_id && c.connection_id !== "default" && <span className="tag" title="Número WhatsApp de origen">{c.connection_id}</span>}
        </div>
      </div>
    </div>
  );
}

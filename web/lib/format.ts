// Helpers de presentación para la bandeja: nombres, canal, estado, tiempos.
import type { Conversation } from "./api";

export type Lead = Record<string, unknown>;

export const CHAN: Record<string, { icon: string; label: string }> = {
  telegram: { icon: "telegram", label: "Telegram" },
  whatsapp: { icon: "whatsapp", label: "WhatsApp" },
  webchat: { icon: "webchat", label: "Webchat" },
};
export const chanOf = (c: { channel: string }) => CHAN[c.channel] || { icon: "webchat", label: c.channel };

/** Estado interno → etiqueta en español + clase de color. */
export function statusLabel(c: { status: string; assigned_to?: string | null }): { text: string; cls: string } {
  if (c.status === "handoff") return { text: c.assigned_to ? `Atiende ${shortEmail(c.assigned_to)}` : "Esperando asesor", cls: "handoff" };
  if (c.status === "closed") return { text: "Cerrado", cls: "closed" };
  return { text: "Con el bot", cls: "bot" };
}

export const shortEmail = (e: string) => (e || "").split("@")[0];

/** `wa:51987654321` → `+51 987 654 321`; `tg:12345` → `Telegram 12345`. */
export function formatRef(ref: string): string {
  if (!ref) return "—";
  const [p, v] = ref.includes(":") ? ref.split(/:(.+)/) : ["", ref];
  if (p === "wa" && /^\d{8,15}$/.test(v)) {
    const cc = v.length > 9 ? v.slice(0, v.length - 9) : "";
    const rest = v.slice(cc.length);
    return `+${cc} ${rest.replace(/(\d{3})(?=\d)/g, "$1 ").trim()}`.trim();
  }
  if (p === "tg") return `Telegram ${v}`;
  return v || ref;
}

/** lead_data de la lista viene como string JSON (SQLite) o como objeto. */
const leadCache = new WeakMap<object, Lead>();
export function leadOf(c: Conversation): Lead {
  const raw = c.lead_data;
  if (!raw) return {};
  if (typeof raw === "object") return raw;
  const hit = leadCache.get(c); if (hit) return hit;
  let parsed: Lead = {};
  try { parsed = JSON.parse(raw) as Lead; } catch { /* noop */ }
  leadCache.set(c, parsed);
  return parsed;
}

/** Nombre a mostrar: nombre del lead si existe, si no la referencia formateada. */
export function displayName(c: Conversation, lead?: Lead | null): string {
  const l = lead && Object.keys(lead).length ? lead : leadOf(c);
  const n = typeof l.nombre === "string" ? l.nombre.trim() : "";
  return n || formatRef(c.user_ref);
}

export const initials = (name: string) => {
  const parts = name.replace(/[^\p{L}\p{N} ]/gu, "").trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return "#";
  return (parts[0][0] + (parts[1]?.[0] || "")).toUpperCase();
};

const AV_COLORS = ["#0a3d91", "#1b9e5a", "#b45309", "#7c3aed", "#0e7490", "#be123c", "#4d7c0f", "#9333ea"];
export function avatarColor(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0;
  return AV_COLORS[h % AV_COLORS.length];
}

const parseTs = (s?: string | null) => {
  if (!s) return null;
  // El backend guarda ISO sin zona (UTC). Lo normalizamos.
  const iso = /Z$|[+-]\d\d:\d\d$/.test(s) ? s : s + "Z";
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
};

/** "ahora", "hace 6 min", "14:32", "ayer", "lun", "03/10". */
export function relTime(s?: string | null, now = Date.now()): string {
  const d = parseTs(s);
  if (!d) return "";
  const diff = Math.max(0, now - d.getTime());
  const min = Math.floor(diff / 60000);
  if (min < 1) return "ahora";
  if (min < 60) return `hace ${min} min`;
  const sameDay = new Date(now).toDateString() === d.toDateString();
  if (sameDay) return d.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" });
  const yest = new Date(now - 86400000);
  if (yest.toDateString() === d.toDateString()) return "ayer";
  if (diff < 6 * 86400000) return d.toLocaleDateString("es", { weekday: "short" });
  return d.toLocaleDateString("es", { day: "2-digit", month: "2-digit" });
}

export function clockTime(s?: string | null): string {
  const d = parseTs(s);
  return d ? d.toLocaleTimeString("es", { hour: "2-digit", minute: "2-digit" }) : "";
}

/** "Hoy", "Ayer" o fecha larga; para separadores en el hilo. */
export function dayLabel(s?: string | null, now = Date.now()): string {
  const d = parseTs(s);
  if (!d) return "";
  const today = new Date(now).toDateString();
  if (d.toDateString() === today) return "Hoy";
  if (d.toDateString() === new Date(now - 86400000).toDateString()) return "Ayer";
  return d.toLocaleDateString("es", { weekday: "long", day: "numeric", month: "long" });
}
export const dayKey = (s?: string | null) => { const d = parseTs(s); return d ? d.toDateString() : ""; };

/** Minutos esperando desde la última actualización (para SLA en handoff). */
export function waitingMinutes(s?: string | null, now = Date.now()): number {
  const d = parseTs(s);
  return d ? Math.floor((now - d.getTime()) / 60000) : 0;
}

export const SLA_WARN_MIN = 5;
export const SLA_LATE_MIN = 15;

export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export const LEAD_LABELS: Record<string, string> = {
  idioma: "Idioma", canal: "Canal", ruta: "Ruta", modo: "Modo",
  monto_enviar: "Monto a enviar", monto_recibir: "Monto a recibir", tasa: "Tasa",
  estado_tc: "Estado TC", aplica_promo: "Promo", tipo_cliente: "Tipo cliente",
  nombre: "Nombre", documento: "Documento", banco_pix: "Banco/PIX", beneficiario: "Beneficiario",
};

export const leadStr = (v: unknown) => (typeof v === "boolean" ? (v ? "Sí" : "No") : v == null ? "" : String(v));

/** Búsqueda local: nombre, referencia, último mensaje. */
export function matches(c: Conversation, q: string, lead?: Lead | null): boolean {
  if (!q) return true;
  const hay = `${displayName(c, lead)} ${c.user_ref} ${c.last_message || ""} ${c.assigned_to || ""}`.toLowerCase();
  return q.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}

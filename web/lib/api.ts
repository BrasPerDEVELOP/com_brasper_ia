// Cliente API tipado hacia el backend FastAPI.
//
// En producción el panel y la API viven en el MISMO dominio: Caddy enruta
// `/api/*`, `/webhook` y `/telegram/webhook/*` al backend y el resto al panel.
// Por eso por defecto usamos rutas relativas (mismo origen): no hay que hornear
// el dominio en el build de Next.js y no hay CORS.
//   - Define NEXT_PUBLIC_API_BASE solo si la API vive en OTRO host/dominio.
//   - En desarrollo cae a http://localhost:8002.
const _RAW = (process.env.NEXT_PUBLIC_API_BASE ?? "").trim().replace(/\/$/, "");
export const API_BASE =
  _RAW !== ""
    ? _RAW
    : process.env.NODE_ENV === "production"
      ? "" // mismo origen -> fetch("/api/...")
      : "http://localhost:8002";

export function getToken(): string {
  if (typeof window === "undefined") return "";
  return localStorage.getItem("cauce_token") || "";
}

export function clearToken() {
  if (typeof window !== "undefined") {
    localStorage.removeItem("cauce_token");
    window.dispatchEvent(new Event("cauce:session-cleared"));
  }
}

/** Construye un query string omitiendo valores vacíos (y codificando "+00:00"). */
export function qs(params: Record<string, string | number | null | undefined>): string {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === "") continue;
    u.set(k, String(v));
  }
  const s = u.toString();
  return s ? `?${s}` : "";
}

export async function api<T = unknown>(path: string, opts: RequestInit = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers as Record<string, string> | undefined) };
  const t = getToken();
  if (t) headers["X-Auth-Token"] = t;
  // FormData (subida de archivos): el navegador pone el Content-Type con boundary.
  if (opts.body && !(opts.body instanceof FormData) && !headers["Content-Type"]) headers["Content-Type"] = "application/json";
  const r = await fetch(API_BASE + path, { ...opts, headers });
  if (r.status === 401) {
    clearToken();
    if (typeof window !== "undefined") window.location.reload();
    throw new Error("Sesión expirada");
  }
  if (!r.ok) {
    let detail: string | null = null;
    try { detail = (await r.json()).detail; } catch { /* noop */ }
    throw new Error(detail || `HTTP ${r.status}`);
  }
  return r.json() as Promise<T>;
}

export async function login(email: string, password: string, code?: string): Promise<{ token: string; user: Me }> {
  const r = await fetch(API_BASE + "/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password: password || undefined, code: code || undefined }),
  });
  if (!r.ok) {
    let detail: string | null = null;
    try { detail = (await r.json()).detail; } catch { /* noop */ }
    throw new Error(typeof detail === "string" && detail ? detail : "Credenciales inválidas");
  }
  return r.json();
}

/** Qué pide el login: el campo de código solo existe mientras dura la transición. */
export interface LoginOptions { password: boolean; legacy_code: boolean; dev_local: boolean }
export async function loginOptions(): Promise<LoginOptions> {
  try {
    const r = await fetch(API_BASE + "/api/login/options");
    if (r.ok) return r.json();
  } catch { /* noop */ }
  return { password: true, legacy_code: false, dev_local: false };
}

/** Cierra la sesión en el servidor (revoca el token) y la borra localmente. */
export async function logout() {
  const t = getToken();
  if (t) {
    try { await fetch(API_BASE + "/api/logout", { method: "POST", headers: { "X-Auth-Token": t } }); } catch { /* noop */ }
  }
  clearToken();
}

export const money = (n: number) =>
  "US$ " + Number(n || 0).toLocaleString("es", { maximumFractionDigits: 4 });

// ---- tipos ----
export interface Me {
  id: number; email: string; name: string; role: string;
  tenant_scope?: string | null; is_agency?: boolean; permissions: string[];
  active?: boolean; has_password?: boolean; must_change_password?: boolean;
}
export interface Tenant {
  id: string; name: string; vertical: string; fee_usd: number; cost_usd: number;
  margin_usd: number; llm_model: string; llm_key_configured: boolean;
  whatsapp_configured: boolean; telegram_configured: boolean; handoff_number: string; calls: number;
  tokens_in: number; tokens_out: number;
}
export interface AdminTenant {
  id: string; name: string; vertical?: string; active?: boolean; fee_usd?: number;
  system_prompt?: string;
  llm?: Record<string, unknown>;
  whatsapp?: Record<string, unknown>;
  telegram?: Record<string, unknown>;
  handoff?: Record<string, unknown>;
}
export interface Conversation {
  id: string; tenant_id: string; channel: string; user_ref: string;
  status: string; updated_at: string; last_message: string; message_count: number;
  assigned_to?: string | null;
  lead_data?: string | Record<string, unknown> | null; // JSON (string en SQLite) con datos del lead
  lead_name?: string | null;     // nombre del lead ya extraído por el backend
  last_role?: string | null;     // role del último mensaje (user = el cliente espera)
  waiting_since?: string | null; // updated_at cuando está en handoff
  tags?: string[];
  connection_id?: string | null; // número WhatsApp (conexión) de origen
}
export interface ConversationsResp { conversations: Conversation[]; count?: number; next_before?: string | null }
export interface MediaRef {
  conversation_id?: string;
  provider: string; kind: string; ref: string;
  mime?: string; name?: string | null; caption?: string;
}
export type Sender = "user" | "bot" | "agent";
export interface Message {
  role: string; content: string; created_at?: string; media?: MediaRef | null;
  sender?: Sender; agent_email?: string | null;
}
export interface Note { id: number; conversation_id: string; author?: string | null; text: string; created_at: string }
export interface ThreadResp {
  conversation_id: string; messages: Message[]; partial?: boolean; lead?: Record<string, unknown>;
  status?: string; assigned_to?: string | null; updated_at?: string; notes?: Note[] | null;
  tags?: string[] | null; connection_id?: string | null;
}
export interface HandoffSummary { reason: string; reason_label: string; extra?: string | null; pending: string; steps: string[]; verified: string[]; text: string; at: string }
export interface Presence { status: "available" | "busy" | "away" | string; last_seen?: string | null; fresh?: boolean }
export interface WaConnection { id: string; label: string; mode: "standard" | "coex"; phone_number_id?: string | null; display_phone?: string | null; configured: boolean }
export interface ToolContract { name: string; description: string; permission: string; timeout_s: number; write: boolean; available: boolean; inputs: Record<string, string>; required: string[] }
export interface KnowledgeEntry { id: string; group: string; lang: string; status: string; question: string; source: string; reviewed_at: string | null }
export interface PublicDocument { id?: number; slug: string; lang: string; version: number; title: string; body_md?: string; status: string; author?: string | null; created_at: string; published_at?: string | null; published_by?: string | null }
export interface DocOverview { slug: string; lang: string; published_version: number | null; published_at: string | null; draft_version: number | null; title: string | null; public_path: string }
export interface DeletionRequest { id: number; contact: string; channel?: string | null; detail?: string | null; status: string; created_at: string; updated_at: string; handled_by?: string | null; note?: string | null }
export interface QuickReply { key: string; title: string; lang: string; text: string }
export interface Advisor { id: number; email: string; name: string; role: string; presence?: Presence }
export interface AdvisorsResp { advisors: Advisor[]; load: Record<string, number>; presence_required?: boolean; presence_ttl_s?: number }

export async function apiBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers["X-Auth-Token"] = t;
  const r = await fetch(API_BASE + path, { headers });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.blob();
}
export interface UsageRow { tenant_id?: string; calls: number; tokens_in: number; tokens_out: number; cost_usd: number; }
export interface UsageDay { day: string; calls: number; tokens_in: number; tokens_out: number; cost_usd: number }
export interface Template { name: string; category: string; language: string; status: string; body: string; variables: number; }
export interface Endpoint { tool: string; method: string; path: string; desc: string; }
export interface Connector { key: string; name: string; base_url: string; endpoints: Endpoint[]; }
export interface OpsAlert { level: "critical" | "warning" | string; code: string; message: string; count?: number; cost_usd?: number; threshold_usd?: number }
export interface OpsMetrics {
  usage: { tenants_with_usage: number; calls: number; cost_usd: number; by_tenant: UsageRow[] };
  conversations: { by_tenant: { count: number }[] };
  messages?: { by_tenant: { count: number }[] };
  appointments?: { by_tenant: { count: number }[] };
  jobs: { dead_letter: number };
  web_vitals?: Record<string, { samples: number; p75: number | null; ratings: Record<string, number> }>;
  flows?: Record<string, { count: number; errors: number; p50_ms: number | null; p95_ms: number | null }>;
}

export function can(me: Me | null, perm: string): boolean {
  const p = me?.permissions || [];
  return p.includes("*") || p.includes(perm) || p.includes(perm.split(":")[0] + ":*");
}

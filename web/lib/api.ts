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
  if (typeof window !== "undefined") localStorage.removeItem("cauce_token");
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

export async function login(email: string, code?: string): Promise<{ token: string; user: Me }> {
  const r = await fetch(API_BASE + "/api/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, code: code || undefined }),
  });
  if (!r.ok) throw new Error("Credenciales inválidas");
  return r.json();
}

export const money = (n: number) =>
  "US$ " + Number(n || 0).toLocaleString("es", { maximumFractionDigits: 4 });

// ---- tipos ----
export interface Me {
  id: number; email: string; name: string; role: string;
  tenant_scope: string | null; is_agency: boolean; permissions: string[];
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
}
export interface MediaRef {
  provider: string; kind: string; ref: string;
  mime?: string; name?: string | null; caption?: string;
}
export interface Message { role: string; content: string; created_at?: string; media?: MediaRef | null; }

export async function apiBlob(path: string): Promise<Blob> {
  const headers: Record<string, string> = {};
  const t = getToken();
  if (t) headers["X-Auth-Token"] = t;
  const r = await fetch(API_BASE + path, { headers });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.blob();
}
export interface UsageRow { tenant_id: string; calls: number; tokens_in: number; tokens_out: number; cost_usd: number; }
export interface Template { name: string; category: string; language: string; status: string; body: string; variables: number; }
export interface Endpoint { tool: string; method: string; path: string; desc: string; }
export interface Connector { key: string; name: string; base_url: string; endpoints: Endpoint[]; }

export function can(me: Me | null, perm: string): boolean {
  const p = me?.permissions || [];
  return p.includes("*") || p.includes(perm) || p.includes(perm.split(":")[0] + ":*");
}

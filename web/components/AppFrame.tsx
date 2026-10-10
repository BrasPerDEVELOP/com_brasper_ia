"use client";
import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { api, login, loginOptions, logout, getToken, clearToken, can, Me, ConversationsResp, LoginOptions } from "@/lib/api";
import Icon from "./Icon";
import Logo from "./Logo";
import { ToastProvider } from "./Toast";
import PasswordForm from "./PasswordForm";

// ---------- contexto del usuario (lo consumen las páginas) ----------
const MeCtx = createContext<Me | null>(null);
export const useMe = () => useContext(MeCtx);

// Rutas públicas (sin login): documentos legales. Nunca redirigen al login.
const PUBLIC_PATHS = ["/privacidad", "/terminos", "/eliminacion-de-datos"];

// perm "" = cualquier usuario autenticado (p.ej. «Mi cuenta»).
type NavItem = { href: string; label: string; icon: string; perm: string };
const GROUPS: { sec: string; items: NavItem[] }[] = [
  { sec: "Operación", items: [
    { href: "/conversaciones", label: "Bandeja", icon: "inbox", perm: "conversations:read" },
    { href: "/chat", label: "Chat de prueba", icon: "chat", perm: "chat:test" },
    { href: "/consumo", label: "Consumo", icon: "creditcard", perm: "usage:read" },
    { href: "/ops", label: "Monitoreo", icon: "chart", perm: "usage:read" },
  ]},
  { sec: "Configuración", items: [
    { href: "/bot", label: "Bot y prompt", icon: "bot", perm: "tenants:write" },
    { href: "/agentes", label: "Agentes de IA", icon: "bot", perm: "config:read" },
    { href: "/promociones", label: "Promociones", icon: "tag", perm: "config:read" },
    { href: "/biblioteca", label: "Imágenes aprobadas", icon: "file", perm: "config:read" },
    { href: "/seguimiento", label: "Encuestas y seguimiento", icon: "clock", perm: "config:read" },
    { href: "/conocimiento", label: "Conocimiento", icon: "note", perm: "conversations:read" },
    { href: "/integraciones", label: "Integraciones", icon: "puzzle", perm: "config:read" },
    { href: "/plantillas", label: "Plantillas", icon: "file", perm: "config:read" },
    { href: "/documentos", label: "Documentos públicos", icon: "tag", perm: "config:read" },
    { href: "/usuarios", label: "Usuarios", icon: "users", perm: "users:read" },
    { href: "/accesos", label: "Accesos", icon: "puzzle", perm: "users:read" },
  ]},
  { sec: "Cuenta", items: [
    { href: "/cuenta", label: "Mi cuenta", icon: "user", perm: "" },
  ]},
];
const TITLES: Record<string, string> = {
  "/conversaciones": "Bandeja de conversaciones", "/ops": "Monitoreo y salud del servicio",
  "/conocimiento": "Conocimiento, herramientas y flags", "/documentos": "Documentos públicos y privacidad", "/accesos": "Accesos por canal, número y sector",
  "/usuarios": "Usuarios, roles y sesiones",
};

// ---------- tema ----------
type Theme = "light" | "dark";
function readTheme(): Theme {
  try {
    const s = localStorage.getItem("brasper_theme");
    if (s === "light" || s === "dark") return s;
  } catch { /* noop */ }
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}
function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try { localStorage.setItem("brasper_theme", t); } catch { /* noop */ }
}

// ---------- login ----------
function LoginScreen({ onLogin }: { onLogin: (m: Me) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [opts, setOpts] = useState<LoginOptions | null>(null);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => { loginOptions().then(setOpts); }, []);
  async function submit() {
    if (!email.trim() || busy) return;
    setBusy(true); setErr("");
    try {
      const d = await login(email.trim(), password, code.trim());
      localStorage.setItem("cauce_token", d.token);
      onLogin(d.user);
    } catch (e) { setErr((e as Error).message); }
    setBusy(false);
  }
  const enter = (e: React.KeyboardEvent) => { if (e.key === "Enter") submit(); };
  return (
    <div className="login-wrap">
      <div>
        <div className="login-box rise">
          <div className="brand"><span className="logo"><Logo /></span><div className="bt"><b>Brasper</b><small>Panel de operación</small></div></div>
          <h2>Hola de nuevo</h2>
          <p className="muted" style={{ margin: "-6px 0 4px", fontSize: 13 }}>Ingresa con tu correo y contraseña de equipo.</p>
          <label className="fld">Email
            <input type="email" value={email} placeholder="tu@brasper.com" autoComplete="username" onChange={e => setEmail(e.target.value)} onKeyDown={enter} />
          </label>
          <label className="fld">Contraseña
            <input type="password" value={password} placeholder="••••••••••" autoComplete="current-password" onChange={e => setPassword(e.target.value)} onKeyDown={enter} />
          </label>
          {opts?.legacy_code && (
            <label className="fld">Código de acceso (solo si aún no tienes contraseña)
              <input type="password" value={code} placeholder="••••••" autoComplete="off" onChange={e => setCode(e.target.value)} onKeyDown={enter} />
            </label>
          )}
          {opts?.dev_local && <p className="muted" style={{ fontSize: 12, margin: 0 }}>Desarrollo local: los usuarios demo sin contraseña entran solo con el email.</p>}
          <button className="btn" onClick={submit} disabled={busy || !email.trim()}>{busy ? "Entrando…" : "Entrar"}</button>
          {err && <div className="err" role="alert">{err}</div>}
        </div>
        <div className="login-foot">Remesas Perú ↔ Brasil · uso interno · <a href="/privacidad" style={{ color: "#fff", textDecoration: "underline" }}>Privacidad</a></div>
      </div>
    </div>
  );
}

// ---------- contraseña temporal: hay que cambiarla antes de usar el panel ----------
function ForcedPasswordChange({ me, onChanged, onExit }: { me: Me; onChanged: (m: Me) => void; onExit: () => void }) {
  return (
    <div className="login-wrap">
      <div>
        <div className="login-box rise">
          <div className="brand"><span className="logo"><Logo /></span><div className="bt"><b>Brasper</b><small>Panel de operación</small></div></div>
          <h2>Cambia tu contraseña</h2>
          <p className="muted" style={{ margin: "-6px 0 4px", fontSize: 13 }}>{me.email} tiene una contraseña temporal. Elige una nueva para continuar.</p>
          <PasswordForm me={me} onChanged={onChanged} />
          <button className="btn btn-ghost" onClick={onExit}>Salir</button>
        </div>
      </div>
    </div>
  );
}

// ---------- presencia del asesor (heartbeat) ----------
type PresenceStatus = "available" | "busy" | "away";
const PRESENCE_LABEL: Record<PresenceStatus, string> = { available: "Disponible", busy: "Ocupado", away: "Ausente" };

function usePresence(me: Me | null) {
  const [status, setStatus] = useState<PresenceStatus>("available");
  useEffect(() => {
    try { const s = localStorage.getItem("brasper_presence"); if (s === "available" || s === "busy" || s === "away") setStatus(s); } catch { /* noop */ }
  }, []);
  useEffect(() => {
    if (!me || !can(me, "conversations:read")) return;
    const beat = () => { if (!document.hidden) api("/api/presence", { method: "POST", body: JSON.stringify({ status }) }).catch(() => {}); };
    beat();
    const t = setInterval(beat, 30000);
    const onVis = () => { if (!document.hidden) beat(); };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearInterval(t); document.removeEventListener("visibilitychange", onVis); };
  }, [me, status]);
  const set = useCallback((s: PresenceStatus) => { setStatus(s); try { localStorage.setItem("brasper_presence", s); } catch { /* noop */ } }, []);
  return { status, set };
}

// ---------- shell ----------
export default function AppFrame({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [theme, setTheme] = useState<Theme>("light");
  const [rail, setRail] = useState(false);
  const [queue, setQueue] = useState(0);
  const pathname = usePathname();
  const isPublic = PUBLIC_PATHS.some(p => pathname === p || pathname.startsWith(p + "/"));
  const presence = usePresence(isPublic ? null : me);

  useEffect(() => {
    setTheme(readTheme());
    try { setRail(localStorage.getItem("brasper_rail") === "1"); } catch { /* noop */ }
    if (isPublic) { setLoading(false); return; }
    if (!getToken()) { setLoading(false); return; }
    api<Me>("/api/me").then(setMe).catch(() => clearToken()).finally(() => setLoading(false));
  }, [isPublic]);

  const toggleTheme = useCallback(() => {
    setTheme(t => { const n: Theme = t === "dark" ? "light" : "dark"; applyTheme(n); return n; });
  }, []);
  const toggleRail = useCallback(() => {
    setRail(r => { try { localStorage.setItem("brasper_rail", r ? "0" : "1"); } catch { /* noop */ } return !r; });
  }, []);

  // Badge de la bandeja: conversaciones en handoff sin asesor (cola). Poll ligero.
  useEffect(() => {
    if (!me || isPublic || !can(me, "conversations:read")) return;
    const tick = () => {
      if (document.hidden) return;
      api<ConversationsResp>("/api/conversations?status=handoff&assigned=none&limit=200")
        .then(d => setQueue(d.conversations.length))
        .catch(() => {});
    };
    tick();
    const t = setInterval(tick, 30000);
    return () => clearInterval(t);
  }, [me, isPublic]);

  // Páginas públicas: sin shell, sin login, sin heartbeat.
  if (isPublic) return <ToastProvider>{children}</ToastProvider>;

  if (loading) return <div className="login-wrap"><div style={{ color: "#fff", opacity: .8 }}>Cargando…</div></div>;
  if (!me) return <ToastProvider><LoginScreen onLogin={setMe} /></ToastProvider>;
  if (me.must_change_password) return <ToastProvider><ForcedPasswordChange me={me} onChanged={setMe} onExit={() => { logout().finally(() => setMe(null)); }} /></ToastProvider>;

  const allowed = (i: NavItem) => !i.perm || can(me, i.perm);
  const allItems = GROUPS.flatMap(g => g.items).filter(allowed);
  const title = TITLES[pathname] || allItems.find(i => i.href === pathname)?.label || "Panel";
  const isInbox = pathname === "/conversaciones";
  const badgeFor = (href: string) => (href === "/conversaciones" && queue > 0 ? <span className="badge" title="Esperando asesor">{queue}</span> : null);

  return (
    <MeCtx.Provider value={me}>
      <ToastProvider>
        <div className={"app" + (rail ? " rail" : "")}>
          <aside className="side">
            <div className="brand">
              <span className="logo"><Logo /></span>
              <div className="bt"><b>Brasper</b><small>Panel</small></div>
            </div>
            <nav className="nav" aria-label="Secciones">
              {GROUPS.map(g => {
                const items = g.items.filter(allowed);
                if (!items.length) return null;
                return (
                  <div key={g.sec}>
                    <div className="nav-sec">{g.sec}</div>
                    {items.map(i => (
                      <Link key={i.href} href={i.href} className={pathname === i.href ? "on" : ""} title={i.label}>
                        <Icon name={i.icon} /><span className="lbl">{i.label}</span>{badgeFor(i.href)}
                      </Link>
                    ))}
                  </div>
                );
              })}
            </nav>
            <div className="side-foot">
              <div className="userrow" title={`${me.name} · ${me.role}`}>
                <div className="av">{(me.name || "?").slice(0, 1).toUpperCase()}</div>
                <div className="grow" style={{ minWidth: 0 }}>
                  <div className="un">{me.name}</div>
                  <div className="ue">{me.role}</div>
                </div>
              </div>
              {can(me, "conversations:read") && (
                <label className={`presence ${presence.status}`} title={`Presencia: ${PRESENCE_LABEL[presence.status]}`} style={{ padding: "0 8px" }}>
                  <span className="dot" />
                  <select value={presence.status} onChange={e => presence.set(e.target.value as PresenceStatus)} aria-label="Estado de presencia">
                    <option value="available">Disponible</option>
                    <option value="busy">Ocupado</option>
                    <option value="away">Ausente</option>
                  </select>
                </label>
              )}
              <div className="foot-actions">
                <button className="ibtn" onClick={toggleTheme} title={theme === "dark" ? "Tema claro" : "Tema oscuro"} aria-label="Cambiar tema">
                  <Icon name={theme === "dark" ? "sun" : "moon"} />
                </button>
                <button className="ibtn" onClick={toggleRail} title={rail ? "Expandir menú" : "Compactar menú"} aria-label="Compactar menú">
                  <Icon name="panel" />
                </button>
                <button className="ibtn" onClick={() => { logout().finally(() => setMe(null)); }} title="Salir" aria-label="Salir">
                  <Icon name="logout" />
                </button>
              </div>
            </div>
          </aside>

          <main className={"main" + (isInbox ? " inbox-page" : "")}>
            <header className="hdr">
              <div className="pt"><span className="k">Brasper</span><span className="v">{title}</span></div>
              <span className="grow" />
              <span className="pill live">En línea</span>
            </header>
            <section className={"content" + (isInbox ? " flush" : "")} key={pathname}>{children}</section>
          </main>

          <nav className="tabbar" aria-label="Secciones">
            {allItems.slice(0, 4).map(i => (
              <Link key={i.href} href={i.href} className={pathname === i.href ? "on" : ""}>
                <Icon name={i.icon} /><span>{i.label}</span>{badgeFor(i.href)}
              </Link>
            ))}
            <a onClick={toggleTheme} role="button" tabIndex={0} aria-label="Cambiar tema">
              <Icon name={theme === "dark" ? "sun" : "moon"} /><span>Tema</span>
            </a>
          </nav>
        </div>
      </ToastProvider>
    </MeCtx.Provider>
  );
}

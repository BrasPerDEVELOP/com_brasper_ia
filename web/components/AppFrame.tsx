"use client";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import Link from "next/link";
import { api, login, getToken, clearToken, can, Me } from "@/lib/api";
import Icon from "./Icon";

type NavItem = { href: string; label: string; icon: string; perm: string };
const GROUPS: { sec: string; items: NavItem[] }[] = [
  { sec: "Operación", items: [
    { href: "/conversaciones", label: "Conversaciones", icon: "inbox", perm: "conversations:read" },
    { href: "/chat", label: "Chat de prueba", icon: "chat", perm: "chat:test" },
    { href: "/consumo", label: "Consumo", icon: "creditcard", perm: "usage:read" },
  ]},
  { sec: "Conexión", items: [
    { href: "/bot", label: "Bot / Prompt", icon: "ai", perm: "tenants:write" },
    { href: "/integraciones", label: "Integraciones", icon: "puzzle", perm: "config:read" },
    { href: "/plantillas", label: "Plantillas", icon: "file", perm: "config:read" },
  ]},
];

function LoginScreen({ onLogin }: { onLogin: (m: Me) => void }) {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [err, setErr] = useState("");
  async function submit() {
    try {
      const d = await login(email.trim(), code.trim());
      localStorage.setItem("cauce_token", d.token);
      onLogin(d.user);
    } catch (e) { setErr((e as Error).message); }
  }
  return (
    <div className="login-wrap">
      <div className="login-box">
        <h2>Brasper · Panel</h2>
        <p className="muted" style={{ margin: "0 0 6px", fontSize: 13 }}>Ingresa con tu email de equipo.</p>
        <input value={email} placeholder="email" onChange={e => setEmail(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") submit(); }} />
        <input value={code} placeholder="código de acceso (si aplica)" onChange={e => setCode(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") submit(); }} />
        <button className="btn" onClick={submit}>Entrar</button>
        {err && <div style={{ color: "var(--danger)", fontSize: 12, marginTop: 8 }}>{err}</div>}
      </div>
    </div>
  );
}

export default function AppFrame({ children }: { children: React.ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const pathname = usePathname();

  useEffect(() => {
    if (!getToken()) { setLoading(false); return; }
    api<Me>("/api/me").then(setMe).catch(() => clearToken()).finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="login-wrap"><div className="muted">Cargando…</div></div>;
  if (!me) return <LoginScreen onLogin={setMe} />;

  const allItems = GROUPS.flatMap(g => g.items);
  const title = allItems.find(i => i.href === pathname)?.label || "Panel";

  return (
    <div className="app">
      <aside className="side">
        <div className="brand">
          <span className="logo">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round"><path d="M4 12c4 0 4-6 8-6s4 12 8 12" /></svg>
          </span>
          <div><b>Brasper</b><small>Panel Admin</small></div>
        </div>
        <nav className="nav">
          {GROUPS.map(g => {
            const items = g.items.filter(i => can(me, i.perm));
            if (!items.length) return null;
            return (
              <div key={g.sec}>
                <div className="nav-sec">{g.sec}</div>
                {items.map(i => (
                  <Link key={i.href} href={i.href} className={pathname === i.href ? "on" : ""}>
                    <Icon name={i.icon} /><span>{i.label}</span>
                  </Link>
                ))}
              </div>
            );
          })}
        </nav>
        <div className="side-foot">
          <div className="userrow">
            <div className="av">{(me.name || "?").slice(0, 1)}</div>
            <div className="grow">
              <div className="un">{me.name}</div>
              <div className="ue">{me.role}</div>
            </div>
          </div>
        </div>
      </aside>
      <main className="main">
        <header className="hdr">
          <div className="pt"><span className="k">Brasper</span><span className="v">{title}</span></div>
          <span className="grow" />
          <button className="btn btn-ghost" onClick={() => { clearToken(); setMe(null); }}>Salir</button>
        </header>
        <section className="content rise" key={pathname}>{children}</section>
      </main>
    </div>
  );
}

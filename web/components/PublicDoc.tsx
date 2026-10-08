"use client";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { Markdown } from "@/lib/markdown";
import Logo from "./Logo";

// Página pública (sin login): muestra SOLO la versión publicada del documento.
// Si no hay versión publicada, lo dice explícitamente en vez de inventar texto legal.
export interface PublicDocData { slug: string; lang: string; version: number; title: string; body_md: string; published_at?: string }

export function usePublicDoc(slug: string) {
  const [doc, setDoc] = useState<PublicDocData | null>(null);
  const [state, setState] = useState<"loading" | "ok" | "missing" | "error">("loading");
  const [lang, setLang] = useState<"es" | "pt">("es");
  useEffect(() => {
    try {
      const p = new URLSearchParams(window.location.search).get("lang");
      if (p === "pt" || p === "es") setLang(p);
    } catch { /* noop */ }
  }, []);
  useEffect(() => {
    let alive = true;
    setState("loading");
    fetch(`${API_BASE}/api/public/documents/${slug}?lang=${lang}`)
      .then(async r => {
        if (!alive) return;
        if (r.status === 404) { setDoc(null); setState("missing"); return; }
        if (!r.ok) { setState("error"); return; }
        setDoc(await r.json()); setState("ok");
      })
      .catch(() => { if (alive) setState("error"); });
    return () => { alive = false; };
  }, [slug, lang]);
  return { doc, state, lang, setLang };
}

export default function PublicDoc({ slug, fallbackTitle, children }: { slug: string; fallbackTitle: string; children?: React.ReactNode }) {
  const { doc, state, lang, setLang } = usePublicDoc(slug);
  const t = lang === "pt"
    ? { preparing: "Documento em preparação", preparingBody: "Esta página ainda não tem uma versão publicada. Para dúvidas sobre privacidade ou seus dados, escreva para a equipe Brasper pelo mesmo canal em que você nos contatou.", updated: "Publicado em", error: "Não foi possível carregar o documento. Tente novamente em alguns minutos." }
    : { preparing: "Documento en preparación", preparingBody: "Esta página aún no tiene una versión publicada. Para consultas sobre privacidad o tus datos, escribe al equipo Brasper por el mismo canal en el que nos contactaste.", updated: "Publicado el", error: "No se pudo cargar el documento. Inténtalo de nuevo en unos minutos." };
  return (
    <div className="public-wrap">
      <header className="public-hd">
        <a href="/privacidad" className="brand" style={{ padding: 0, height: "auto", border: "none" }}>
          <span className="logo"><Logo /></span><div className="bt"><b>Brasper</b><small>Transferencias</small></div>
        </a>
        <nav aria-label="Documentos" className="public-nav">
          <a href={`/privacidad${lang === "pt" ? "?lang=pt" : ""}`}>{lang === "pt" ? "Privacidade" : "Privacidad"}</a>
          <a href={`/terminos${lang === "pt" ? "?lang=pt" : ""}`}>{lang === "pt" ? "Termos" : "Términos"}</a>
          <a href={`/eliminacion-de-datos${lang === "pt" ? "?lang=pt" : ""}`}>{lang === "pt" ? "Exclusão de dados" : "Eliminación de datos"}</a>
          <span className="seg" role="tablist" aria-label="Idioma">
            <button role="tab" aria-selected={lang === "es"} className={lang === "es" ? "on" : ""} onClick={() => setLang("es")}>ES</button>
            <button role="tab" aria-selected={lang === "pt"} className={lang === "pt" ? "on" : ""} onClick={() => setLang("pt")}>PT</button>
          </span>
        </nav>
      </header>
      <main className="public-main">
        {state === "loading" && <div className="sk" style={{ height: 180 }} />}
        {state === "error" && <div className="usage-note err">{t.error}</div>}
        {state === "missing" && (
          <article>
            <h1>{fallbackTitle}</h1>
            <div className="usage-note" style={{ marginTop: 12 }}><b>{t.preparing}.</b> {t.preparingBody}</div>
          </article>
        )}
        {state === "ok" && doc && (
          <article>
            <h1>{doc.title}</h1>
            {doc.published_at && <p className="muted" style={{ fontSize: 12.5 }}>{t.updated} {doc.published_at.slice(0, 10)} · v{doc.version}</p>}
            <Markdown text={doc.body_md} />
          </article>
        )}
        {children}
      </main>
      <footer className="public-foot">© {new Date().getFullYear()} Brasper Transferencias · <a href="/privacidad">Privacidad</a> · <a href="/terminos">Términos</a> · <a href="/eliminacion-de-datos">Eliminación de datos</a></footer>
    </div>
  );
}

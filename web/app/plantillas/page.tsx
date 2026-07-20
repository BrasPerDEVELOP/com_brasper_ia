"use client";
import { useEffect, useState } from "react";
import { api, Template } from "@/lib/api";
import TenantSelect from "@/components/TenantSelect";

export default function Plantillas() {
  const [tenant, setTenant] = useState("");
  const [tpls, setTpls] = useState<Template[]>([]);
  const [form, setForm] = useState({ to: "", template_name: "", params: "", language: "" });
  const [out, setOut] = useState("");
  useEffect(() => {
    if (!tenant) return;
    api<{ templates: Template[] }>(`/api/${tenant}/templates`).then(d => setTpls(d.templates)).catch(() => setTpls([]));
  }, [tenant]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const params = form.params.split(",").map(s => s.trim()).filter(Boolean);
    const body: Record<string, unknown> = { to: form.to.trim(), template_name: form.template_name.trim(), params };
    if (form.language.trim()) body.language = form.language.trim();
    try {
      const r = await api(`/api/${tenant}/templates/send`, { method: "POST", body: JSON.stringify(body) });
      setOut(JSON.stringify(r, null, 2));
    } catch (err) { setOut("⚠️ " + (err as Error).message); }
  }

  return (
    <>
      <div className="usage-note">Plantillas HSM: los únicos mensajes que puedes iniciar fuera de la ventana de 24 h. El envío real requiere el token de WhatsApp del cliente.</div>
      <div className="row"><label className="muted">Cliente:</label><TenantSelect value={tenant} onChange={setTenant} /></div>
      <table><thead><tr><th>Nombre</th><th>Categoría</th><th>Idioma</th><th>Estado</th><th className="num">Vars</th><th>Cuerpo</th></tr></thead>
        <tbody>{tpls.length ? tpls.map(t => (
          <tr key={t.name}><td className="mono" style={{ fontSize: 12 }}>{t.name}</td><td><span className="tag">{t.category}</span></td><td className="muted">{t.language}</td><td><span className="tag" style={{ background: "var(--accent-soft)", color: "var(--accent-d)" }}>{t.status}</span></td><td className="num">{t.variables}</td><td style={{ fontSize: 12 }}>{t.body}</td></tr>
        )) : <tr><td colSpan={6} className="empty">Sin plantillas</td></tr>}</tbody></table>
      <h3 className="sec-title">Enviar plantilla</h3>
      <form className="row" onSubmit={send}>
        <input placeholder="Número destino (51...)" required value={form.to} onChange={e => setForm({ ...form, to: e.target.value })} />
        <input placeholder="Nombre de plantilla" required value={form.template_name} onChange={e => setForm({ ...form, template_name: e.target.value })} />
        <input placeholder="Parámetros (coma)" value={form.params} onChange={e => setForm({ ...form, params: e.target.value })} />
        <input placeholder="Idioma (ej. es)" style={{ width: 100 }} value={form.language} onChange={e => setForm({ ...form, language: e.target.value })} />
        <button className="btn" type="submit">Enviar</button>
      </form>
      {out && <pre className="out">{out}</pre>}
    </>
  );
}

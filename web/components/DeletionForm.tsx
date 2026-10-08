"use client";
import { useState } from "react";
import { API_BASE } from "@/lib/api";

// Canal operativo de solicitud de eliminación: registra la solicitud para que el
// equipo verifique la identidad. NO borra datos automáticamente.
export default function DeletionForm() {
  const [contact, setContact] = useState("");
  const [channel, setChannel] = useState("whatsapp");
  const [detail, setDetail] = useState("");
  const [state, setState] = useState<"idle" | "sending" | "done" | "error">("idle");
  const [result, setResult] = useState<{ id: number; received_at: string } | null>(null);
  const [err, setErr] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (contact.trim().length < 5 || state === "sending") return;
    setState("sending"); setErr("");
    try {
      const r = await fetch(`${API_BASE}/api/public/data-deletion-request`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contact: contact.trim(), channel, detail: detail.trim() || undefined }),
      });
      if (!r.ok) { let d = ""; try { d = (await r.json()).detail; } catch { /* noop */ } throw new Error(d || `HTTP ${r.status}`); }
      setResult(await r.json()); setState("done");
    } catch (ex) { setErr((ex as Error).message); setState("error"); }
  }

  if (state === "done" && result) {
    return (
      <section className="card" style={{ marginTop: 20 }}>
        <h3>Solicitud recibida</h3>
        <p>Registramos tu solicitud con el número <b className="mono">#{result.id}</b> el {result.received_at.slice(0, 10)}. Antes de eliminar datos verificaremos tu identidad por el canal indicado; te responderemos por ese mismo medio.</p>
      </section>
    );
  }
  return (
    <section className="card" style={{ marginTop: 20 }}>
      <h3>Solicitar la eliminación de mis datos</h3>
      <p className="muted" style={{ fontSize: 13.5 }}>Indica el teléfono o correo con el que te comunicaste con Brasper. Verificaremos tu identidad antes de eliminar información; algunos registros pueden conservarse por obligaciones legales, lo que te explicaremos en la respuesta.</p>
      <form onSubmit={submit} style={{ display: "grid", gap: 10, maxWidth: 480 }}>
        <label className="fld">Teléfono o correo
          <input value={contact} onChange={e => setContact(e.target.value)} placeholder="+51 999 999 999 o nombre@correo.com" required minLength={5} maxLength={200} />
        </label>
        <label className="fld">Canal por el que nos escribiste
          <select value={channel} onChange={e => setChannel(e.target.value)}>
            <option value="whatsapp">WhatsApp</option>
            <option value="telegram">Telegram</option>
            <option value="web">Chat web</option>
            <option value="otro">Otro</option>
          </select>
        </label>
        <label className="fld">Detalle (opcional)
          <textarea rows={3} value={detail} onChange={e => setDetail(e.target.value)} maxLength={2000} placeholder="Qué datos quieres eliminar" />
        </label>
        <button className="btn" type="submit" disabled={state === "sending" || contact.trim().length < 5}>{state === "sending" ? "Enviando…" : "Enviar solicitud"}</button>
        {err && <div className="usage-note err" style={{ margin: 0 }}>{err}</div>}
      </form>
    </section>
  );
}

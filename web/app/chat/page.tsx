"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/api";
import TenantSelect from "@/components/TenantSelect";
import Icon from "@/components/Icon";

interface Bubble { role: "user" | "assistant"; text: string; meta?: string; }
interface ChatResp { response: string; conversation_id: string; handoff: boolean; usage: { tokens_in: number; tokens_out: number; cost_usd: number; model: string } | null; }

export default function Chat() {
  const [tenant, setTenant] = useState("");
  const [bubbles, setBubbles] = useState<Bubble[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const convId = useRef<string | null>(null);

  function onTenant(id: string) { setTenant(id); setBubbles([]); convId.current = null; }

  async function send() {
    const msg = text.trim();
    if (!msg || !tenant || busy) return;
    setText(""); setBusy(true);
    setBubbles(b => [...b, { role: "user", text: msg }]);
    try {
      const r = await api<ChatResp>(`/api/${tenant}/chat`, {
        method: "POST",
        body: JSON.stringify({ message: msg, user_ref: "panel-test", conversation_id: convId.current }),
      });
      convId.current = r.conversation_id;
      const meta = r.handoff ? "handoff · sin costo LLM"
        : r.usage ? `${r.usage.model} · ${r.usage.tokens_in}→${r.usage.tokens_out} tok · US$ ${r.usage.cost_usd}` : "";
      setBubbles(b => [...b, { role: "assistant", text: r.response, meta }]);
    } catch (e) {
      setBubbles(b => [...b, { role: "assistant", text: "⚠️ " + (e as Error).message }]);
    } finally { setBusy(false); }
  }

  return (
    <>
      <div className="row"><label className="muted">Probar como cliente:</label><TenantSelect value={tenant} onChange={onTenant} />
        <span className="pill live">LLM real · queda persistido y medido</span></div>
      <div className="thread" style={{ height: "calc(100vh - 200px)" }}>
        <div className="msgs">
          {bubbles.length ? bubbles.map((b, i) => (
            <div key={i} className={"msg " + b.role}>{b.text}{b.meta && <small>{b.meta}</small>}</div>
          )) : <div className="empty">Escribe abajo — cada respuesta llama al bot real y cuesta una fracción de centavo.</div>}
          {busy && <div className="msg assistant">…</div>}
        </div>
        <div className="chatbar">
          <input value={text} placeholder="Escribe un mensaje…" onChange={e => setText(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") send(); }} />
          <button className="btn" onClick={send} disabled={busy}><Icon name="send" size={16} /></button>
        </div>
      </div>
    </>
  );
}

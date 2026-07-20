"use client";
import { useEffect, useState } from "react";
import { api, Connector, Endpoint, Tenant } from "@/lib/api";
import TenantSelect from "@/components/TenantSelect";

type TgInfo = {
  getMe?: { ok?: boolean; result?: { username?: string; first_name?: string }; reason?: string; detail?: string };
  webhook?: { ok?: boolean; result?: { url?: string } };
};

function TelegramStatus({ tenant, configured }: { tenant: string; configured: boolean }) {
  const [state, setState] = useState<"idle" | "loading" | "done">("idle");
  const [info, setInfo] = useState<TgInfo | null>(null);
  const [err, setErr] = useState("");

  async function test() {
    setState("loading"); setErr(""); setInfo(null);
    try {
      setInfo(await api<TgInfo>(`/api/${tenant}/telegram/info`));
    } catch (e) { setErr((e as Error).message); }
    setState("done");
  }

  const me = info?.getMe;
  const ok = me?.ok === true;
  const username = me?.result?.username;
  const webhookUrl = info?.webhook?.result?.url;

  return (
    <div style={{ borderTop: "1px solid var(--line)", paddingTop: 10, marginTop: 10 }}>
      <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
        <b style={{ fontSize: 13 }}>Telegram</b>
        <span className={"tag" + (configured ? "" : " handoff")}>
          {configured ? "token configurado" : "sin token"}
        </span>
        <span className="grow" />
        <button className="btn" style={{ padding: "5px 12px" }} onClick={test} disabled={state === "loading"}>
          {state === "loading" ? "Probando…" : "Probar conexión"}
        </button>
      </div>

      {state === "done" && (
        <div style={{ marginTop: 8, fontSize: 13 }}>
          {err ? <span style={{ color: "var(--danger)" }}>⚠️ {err}</span>
            : ok ? (
              <div style={{ color: "var(--ok, #0c5743)" }}>
                ✅ <b>Conectado correctamente</b> como <b>@{username}</b>.
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  {webhookUrl ? <>Webhook activo: <code className="mono">{webhookUrl}</code></>
                    : "Sin webhook (modo polling local con dev_telegram.py)."}
                </div>
              </div>
            ) : (
              <div style={{ color: "var(--danger)" }}>
                ❌ No conectado — {me?.reason || me?.detail || "revisa el token"}.
                <div className="muted" style={{ fontSize: 12, marginTop: 4 }}>
                  Crea el bot con @BotFather y pon <code className="mono">TELEGRAM_TOKEN_{tenant.toUpperCase()}</code> en backend/.env.
                </div>
              </div>
            )}
        </div>
      )}
      {state === "idle" && !configured && (
        <p className="muted" style={{ fontSize: 12, marginTop: 6 }}>
          Aún no hay token. Crea el bot con @BotFather y añade <code className="mono">TELEGRAM_TOKEN_{tenant.toUpperCase()}</code>.
        </p>
      )}
    </div>
  );
}

function EndpointRow({ tenant, ck, ep }: { tenant: string; ck: string; ep: Endpoint }) {
  const vars = (ep.path.match(/\{\{\s*([a-zA-Z0-9_]+)\s*\}\}/g) || []).map(m => m.replace(/[{}\s]/g, ""));
  const [vals, setVals] = useState<Record<string, string>>({});
  const [out, setOut] = useState<string>("");
  async function test() {
    setOut("Llamando…");
    try {
      const r = await api(`/api/${tenant}/connectors/${ck}/${ep.tool}/test`, {
        method: "POST", body: JSON.stringify({ variables: vals }),
      });
      setOut(JSON.stringify(r, null, 2));
    } catch (e) { setOut("⚠️ " + (e as Error).message); }
  }
  return (
    <div style={{ margin: "8px 0", paddingTop: 8, borderTop: "1px solid var(--line)" }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center", flexWrap: "wrap" }}>
        <span className="tag mono">{ep.method}</span>
        <code className="mono" style={{ fontSize: 12 }}>{ep.path}</code>
        <span className="muted grow" style={{ fontSize: 12 }}>{ep.desc}</span>
        {vars.map(v => <input key={v} placeholder={v} style={{ width: 110, padding: "5px 8px" }}
          onChange={e => setVals(s => ({ ...s, [v]: e.target.value }))} />)}
        <button className="btn" style={{ padding: "5px 12px" }} onClick={test}>Probar</button>
      </div>
      {out && <pre className="out">{out}</pre>}
    </div>
  );
}

export default function Integraciones() {
  const [tenant, setTenant] = useState("");
  const [connectors, setConnectors] = useState<Connector[]>([]);
  const [flags, setFlags] = useState<Tenant | null>(null);
  useEffect(() => {
    if (!tenant) return;
    api<{ connectors: Connector[] }>(`/api/${tenant}/connectors`).then(d => setConnectors(d.connectors)).catch(() => setConnectors([]));
    api<{ tenants: Tenant[] }>("/api/tenants").then(d => setFlags(d.tenants.find(t => t.id === tenant) || null)).catch(() => setFlags(null));
  }, [tenant]);
  return (
    <>
      <div className="usage-note">Canales de mensajería y conectores de API por cliente. El botón &quot;Probar conexión&quot; consulta el servicio real (Telegram / httpbin), no es simulado.</div>
      <div className="row"><label className="muted">Cliente:</label><TenantSelect value={tenant} onChange={setTenant} /></div>

      {tenant && (
        <div className="card" style={{ marginBottom: 12 }}>
          <h3>Canales de mensajería</h3>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <b style={{ fontSize: 13 }}>WhatsApp</b>
            <span className={"tag" + (flags?.whatsapp_configured ? "" : " handoff")}>
              {flags?.whatsapp_configured ? "credenciales configuradas" : "pendiente (credenciales de Meta)"}
            </span>
          </div>
          <TelegramStatus tenant={tenant} configured={!!flags?.telegram_configured} />
        </div>
      )}

      {connectors.length ? connectors.map(c => (
        <div className="card" key={c.key} style={{ marginBottom: 12 }}>
          <h3>{c.name} <small className="muted" style={{ fontSize: 11, fontWeight: 400 }}>{c.base_url}</small></h3>
          {c.endpoints.map(ep => <EndpointRow key={ep.tool} tenant={tenant} ck={c.key} ep={ep} />)}
        </div>
      )) : tenant ? <div className="empty">Este cliente no tiene conectores de API configurados.</div> : null}
    </>
  );
}

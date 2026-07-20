"use client";
import { useEffect, useMemo, useState } from "react";
import { AdminTenant, api, can, Me, money, Tenant } from "@/lib/api";

type AdminList = { source: string; tenants: AdminTenant[] };
type FormState = {
  id: string;
  name: string;
  vertical: string;
  fee_usd: string;
  active: boolean;
  llm_provider: string;
  llm_model: string;
  llm_api_key_env: string;
  whatsapp_phone_number_id_env: string;
  whatsapp_token_env: string;
  telegram_bot_token_env: string;
  telegram_secret_token_env: string;
  handoff_number: string;
  system_prompt: string;
};

const EMPTY_FORM: FormState = {
  id: "",
  name: "",
  vertical: "",
  fee_usd: "0",
  active: true,
  llm_provider: "deepseek",
  llm_model: "deepseek-chat",
  llm_api_key_env: "DEEPSEEK_API_KEY",
  whatsapp_phone_number_id_env: "",
  whatsapp_token_env: "",
  telegram_bot_token_env: "",
  telegram_secret_token_env: "",
  handoff_number: "",
  system_prompt: "",
};

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function tenantToForm(t: AdminTenant): FormState {
  const llm = t.llm || {};
  const wa = t.whatsapp || {};
  const tg = t.telegram || {};
  const handoff = t.handoff || {};
  return {
    id: t.id,
    name: t.name || "",
    vertical: t.vertical || "",
    fee_usd: String(t.fee_usd ?? 0),
    active: t.active !== false,
    llm_provider: str(llm.provider) || "deepseek",
    llm_model: str(llm.model) || "deepseek-chat",
    llm_api_key_env: str(llm.api_key_env),
    whatsapp_phone_number_id_env: str(wa.phone_number_id_env),
    whatsapp_token_env: str(wa.token_env),
    telegram_bot_token_env: str(tg.bot_token_env),
    telegram_secret_token_env: str(tg.secret_token_env),
    handoff_number: str(handoff.number),
    system_prompt: t.system_prompt || "",
  };
}

function configFromForm(f: FormState) {
  const config: Record<string, unknown> = {
    name: f.name.trim(),
    vertical: f.vertical.trim(),
    active: f.active,
    fee_usd: Number(f.fee_usd || 0),
  };
  if (f.system_prompt.trim()) config.system_prompt = f.system_prompt.trim();
  config.llm = {
    provider: f.llm_provider.trim() || "deepseek",
    model: f.llm_model.trim() || "deepseek-chat",
    api_key_env: f.llm_api_key_env.trim(),
    temperature: 0.7,
    max_tokens: 500,
  };
  if (f.whatsapp_phone_number_id_env.trim() || f.whatsapp_token_env.trim()) {
    config.whatsapp = {
      phone_number_id_env: f.whatsapp_phone_number_id_env.trim(),
      token_env: f.whatsapp_token_env.trim(),
    };
  }
  if (f.telegram_bot_token_env.trim() || f.telegram_secret_token_env.trim()) {
    config.telegram = {
      bot_token_env: f.telegram_bot_token_env.trim(),
      secret_token_env: f.telegram_secret_token_env.trim(),
    };
  }
  if (f.handoff_number.trim()) {
    config.handoff = {
      number: f.handoff_number.trim(),
      keywords: ["asesor", "humano", "persona real", "advisor"],
      message: "Con gusto te conecto con un asesor: https://wa.me/{number}",
    };
  }
  return config;
}

export default function Clientes() {
  const [me, setMe] = useState<Me | null>(null);
  const [tenants, setTenants] = useState<Tenant[]>([]);
  const [admin, setAdmin] = useState<AdminList | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [editing, setEditing] = useState("");
  const [err, setErr] = useState("");
  const [adminErr, setAdminErr] = useState("");
  const [saving, setSaving] = useState(false);

  const adminById = useMemo(() => {
    const map = new Map<string, AdminTenant>();
    (admin?.tenants || []).forEach(t => map.set(t.id, t));
    return map;
  }, [admin]);

  async function load() {
    setErr("");
    setAdminErr("");
    try {
      const [tenantData, user] = await Promise.all([
        api<{ tenants: Tenant[] }>("/api/tenants"),
        api<Me>("/api/me"),
      ]);
      setTenants(tenantData.tenants);
      setMe(user);
      if (can(user, "tenants:write")) {
        const adminData = await api<AdminList>("/api/admin/tenants");
        setAdmin(adminData);
      }
    } catch (e) {
      setErr((e as Error).message);
    }
  }

  useEffect(() => { load(); }, []);

  function edit(t: AdminTenant) {
    setEditing(t.id);
    setForm(tenantToForm(t));
    setAdminErr("");
  }

  function resetForm() {
    setEditing("");
    setForm(EMPTY_FORM);
    setAdminErr("");
  }

  async function saveTenant() {
    if (!form.id.trim() || !form.name.trim()) {
      setAdminErr("Faltan id y nombre.");
      return;
    }
    setSaving(true);
    setAdminErr("");
    try {
      const body = JSON.stringify({ config: configFromForm(form) });
      if (editing) {
        await api(`/api/admin/tenants/${editing}`, { method: "PATCH", body });
      } else {
        await api("/api/admin/tenants", {
          method: "POST",
          body: JSON.stringify({ id: form.id.trim(), config: configFromForm(form) }),
        });
      }
      resetForm();
      await load();
    } catch (e) {
      setAdminErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function setActive(t: AdminTenant, active: boolean) {
    setSaving(true);
    setAdminErr("");
    try {
      await api(`/api/admin/tenants/${t.id}/${active ? "resume" : "pause"}`, { method: "POST" });
      await load();
    } catch (e) {
      setAdminErr((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (err) return <div className="empty">Error: {err}</div>;

  return (
    <>
      <div className="usage-note">Cada cliente (tenant) con su configuración real y consumo medido. En producción la configuración se administra desde Postgres; los secretos se referencian por variables de entorno.</div>
      <div className="cards">
        {tenants.map(t => {
          const raw = adminById.get(t.id);
          return (
            <div className="card" key={t.id}>
              <div className="card-head">
                <div>
                  <h3>{t.name}</h3>
                  <div className="muted" style={{ fontSize: 12 }}>{t.vertical} · <span className="mono">{t.id}</span></div>
                </div>
                <span className={"tag" + (raw?.active === false ? " handoff" : "")}>{raw?.active === false ? "pausado" : "activo"}</span>
              </div>
              <div className="kv"><span className="muted">Fee mensual</span><b>{money(t.fee_usd)}</b></div>
              <div className="kv"><span className="muted">Costo IA</span><b className="bad">{money(t.cost_usd)}</b></div>
              <div className="kv"><span className="muted">Margen</span><b className="ok">{money(t.margin_usd)}</b></div>
              <div className="kv"><span className="muted">Modelo</span><b style={{ fontSize: 12 }}>{t.llm_model}</b></div>
              <div className="kv"><span className="muted">Key LLM</span><span className={"tag" + (t.llm_key_configured ? "" : " handoff")}>{t.llm_key_configured ? "configurada" : "falta"}</span></div>
              <div className="kv"><span className="muted">WhatsApp</span><span className={"tag" + (t.whatsapp_configured ? "" : " handoff")}>{t.whatsapp_configured ? "conectado" : "pendiente"}</span></div>
              <div className="kv"><span className="muted">Telegram</span><span className={"tag" + (t.telegram_configured ? "" : " handoff")}>{t.telegram_configured ? "conectado" : "pendiente"}</span></div>
              <div className="kv"><span className="muted">Handoff</span><b style={{ fontSize: 12 }}>{t.handoff_number ? "+" + t.handoff_number : "sin número"}</b></div>
              {admin && (
                <div className="row" style={{ marginTop: 12, marginBottom: 0 }}>
                  <button className="btn btn-ghost" onClick={() => raw && edit(raw)}>Editar</button>
                  {raw && <button className="btn btn-ghost" disabled={saving} onClick={() => setActive(raw, raw.active === false)}>{raw.active === false ? "Reanudar" : "Pausar"}</button>}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {admin && (
        <div className="admin-panel">
          <div className="card">
            <div className="card-head">
              <div>
                <h3>{editing ? "Editar cliente" : "Crear cliente"}</h3>
                <div className="muted" style={{ fontSize: 12 }}>Fuente: <span className="mono">{admin.source}</span></div>
              </div>
              <button className="btn btn-ghost" onClick={resetForm}>Nuevo</button>
            </div>
            <div className="form-grid">
              <label>ID<input value={form.id} disabled={!!editing} onChange={e => setForm(s => ({ ...s, id: e.target.value }))} placeholder="cliente_demo" /></label>
              <label>Nombre<input value={form.name} onChange={e => setForm(s => ({ ...s, name: e.target.value }))} placeholder="Cliente Demo" /></label>
              <label>Vertical<input value={form.vertical} onChange={e => setForm(s => ({ ...s, vertical: e.target.value }))} placeholder="Salud, retail, servicios..." /></label>
              <label>Fee US$<input value={form.fee_usd} type="number" min="0" onChange={e => setForm(s => ({ ...s, fee_usd: e.target.value }))} /></label>
              <label>Provider IA<input value={form.llm_provider} onChange={e => setForm(s => ({ ...s, llm_provider: e.target.value }))} /></label>
              <label>Modelo<input value={form.llm_model} onChange={e => setForm(s => ({ ...s, llm_model: e.target.value }))} /></label>
              <label>LLM API env<input value={form.llm_api_key_env} onChange={e => setForm(s => ({ ...s, llm_api_key_env: e.target.value }))} placeholder="OPENAI_API_KEY_CLIENTE" /></label>
              <label>Handoff WhatsApp<input value={form.handoff_number} onChange={e => setForm(s => ({ ...s, handoff_number: e.target.value }))} placeholder="51999999999" /></label>
              <label>WA phone env<input value={form.whatsapp_phone_number_id_env} onChange={e => setForm(s => ({ ...s, whatsapp_phone_number_id_env: e.target.value }))} /></label>
              <label>WA token env<input value={form.whatsapp_token_env} onChange={e => setForm(s => ({ ...s, whatsapp_token_env: e.target.value }))} /></label>
              <label>TG bot env<input value={form.telegram_bot_token_env} onChange={e => setForm(s => ({ ...s, telegram_bot_token_env: e.target.value }))} /></label>
              <label>TG secret env<input value={form.telegram_secret_token_env} onChange={e => setForm(s => ({ ...s, telegram_secret_token_env: e.target.value }))} /></label>
            </div>
            <label className="prompt-label">Prompt base<textarea value={form.system_prompt} onChange={e => setForm(s => ({ ...s, system_prompt: e.target.value }))} placeholder="Describe cómo debe responder el bot de este cliente." /></label>
            <div className="row" style={{ marginBottom: 0 }}>
              <label className="check"><input type="checkbox" checked={form.active} onChange={e => setForm(s => ({ ...s, active: e.target.checked }))} /> Activo</label>
              <button className="btn" disabled={saving} onClick={saveTenant}>{saving ? "Guardando..." : editing ? "Guardar cambios" : "Crear cliente"}</button>
              {adminErr && <span className="bad" style={{ fontSize: 12 }}>{adminErr}</span>}
            </div>
          </div>

          <div className="card">
            <h3>Todos los tenants</h3>
            <table style={{ marginTop: 10 }}>
              <thead><tr><th>ID</th><th>Nombre</th><th>Estado</th><th>Modelo</th><th /></tr></thead>
              <tbody>
                {admin.tenants.map(t => (
                  <tr key={t.id}>
                    <td className="mono">{t.id}</td>
                    <td>{t.name}</td>
                    <td><span className={"tag" + (t.active === false ? " handoff" : "")}>{t.active === false ? "pausado" : "activo"}</span></td>
                    <td className="mono">{str(t.llm?.model) || "sin modelo"}</td>
                    <td className="num"><button className="btn btn-ghost" onClick={() => edit(t)}>Editar</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </>
  );
}

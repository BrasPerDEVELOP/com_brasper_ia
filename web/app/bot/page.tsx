"use client";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import TenantSelect from "@/components/TenantSelect";

/* Configuración del bot por cliente: prompt, LLM, handoff y cotizador.
   Guarda vía PATCH /api/admin/tenants/{id} (deep-merge en el backend). */

type AdminTenant = {
  id: string; name?: string; vertical?: string; active?: boolean;
  system_prompt?: string;
  llm?: { provider?: string; model?: string; temperature?: number; max_tokens?: number; base_url?: string; api_key_env?: string };
  handoff?: { number?: string; keywords?: string[]; message?: string };
  quote?: {
    enabled?: boolean;
    pairs?: [string, string][];
    rates?: Record<string, number>;
    commission_ranges?: { min: number; max: number; rate: number }[];
    coupon?: { code?: string; discount_percentage?: number };
  };
};

type LiveRate = { origin: string; destination: string; pair: string; rate: number; updated_at?: string | null };

export default function BotConfig() {
  const [tenant, setTenant] = useState("");
  const [cfg, setCfg] = useState<AdminTenant | null>(null);
  const [saving, setSaving] = useState(false);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);
  const [liveRates, setLiveRates] = useState<LiveRate[]>([]);
  const [ratesNote, setRatesNote] = useState("Cargando tasas de Brasper…");

  useEffect(() => {
    if (!tenant) return;
    setNote(null);
    api<{ tenants: AdminTenant[] }>("/api/admin/tenants")
      .then(d => {
        const t = d.tenants.find(x => x.id === tenant) || null;
        setCfg(t);
      })
      .catch(e => setNote({ ok: false, text: (e as Error).message }));
    setLiveRates([]);
    setRatesNote("Cargando tasas de Brasper…");
    api<{ source: string; rates: LiveRate[] }>(`/api/admin/tenants/${tenant}/quote-rates`)
      .then(d => { setLiveRates(d.rates); setRatesNote(`Fuente: ${d.source}`); })
      .catch(e => setRatesNote(`No se pudieron cargar las tasas: ${(e as Error).message}`));
  }, [tenant]);

  function set<K extends keyof AdminTenant>(key: K, value: AdminTenant[K]) {
    setCfg(c => (c ? { ...c, [key]: value } : c));
  }
  const llm = cfg?.llm ?? {};
  const handoff = cfg?.handoff ?? {};
  const quote = cfg?.quote ?? {};

  async function save() {
    if (!cfg) return;
    setSaving(true); setNote(null);
    const body = {
      config: {
        system_prompt: cfg.system_prompt ?? "",
        llm: { model: llm.model, temperature: Number(llm.temperature ?? 0.7), max_tokens: Number(llm.max_tokens ?? 500) },
        handoff: { number: handoff.number ?? "", keywords: handoff.keywords ?? [], message: handoff.message ?? "" },
        quote: { enabled: !!quote.enabled },
      },
    };
    try {
      await api(`/api/admin/tenants/${tenant}`, { method: "PATCH", body: JSON.stringify(body) });
      setNote({ ok: true, text: "Guardado. El bot ya responde con esta configuración." });
    } catch (e) { setNote({ ok: false, text: (e as Error).message }); }
    setSaving(false);
  }

  return (
    <>
      <div className="row"><label className="muted">Cliente:</label><TenantSelect value={tenant} onChange={setTenant} />
        <span className="grow" />
        <button className="btn" onClick={save} disabled={saving || !cfg}>{saving ? "Guardando…" : "Guardar cambios"}</button>
      </div>
      {note && <div className="usage-note" style={!note.ok ? { background: "#fdecec", color: "#8f1d1d" } : undefined}>{note.text}</div>}
      {!cfg ? <div className="empty">Selecciona un cliente.</div> : (
        <div className="cards" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(340px, 1fr))" }}>
          <div className="card">
            <h3>Prompt del sistema</h3>
            <p className="muted" style={{ fontSize: 12, margin: "0 0 6px" }}>Define la personalidad y reglas del bot. Se envía en cada llamada al LLM.</p>
            <textarea rows={9} style={{ width: "100%", fontFamily: "var(--mono)", fontSize: 12 }}
              value={cfg.system_prompt ?? ""} onChange={e => set("system_prompt", e.target.value)} />
          </div>

          <div className="card">
            <h3>Modelo de IA</h3>
            <div className="kv"><span className="muted">Proveedor</span><b>{llm.provider ?? "—"} <span className="muted" style={{ fontSize: 11 }}>(key: {llm.api_key_env ?? "—"})</span></b></div>
            <label className="muted" style={{ fontSize: 12 }}>Modelo</label>
            <input value={llm.model ?? ""} onChange={e => set("llm", { ...llm, model: e.target.value })} />
            <div className="row" style={{ gap: 10, marginTop: 8 }}>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12 }}>Temperatura</label>
                <input type="number" step="0.1" min="0" max="2" value={llm.temperature ?? 0.7}
                  onChange={e => set("llm", { ...llm, temperature: Number(e.target.value) })} />
              </div>
              <div style={{ flex: 1 }}>
                <label className="muted" style={{ fontSize: 12 }}>Máx. tokens</label>
                <input type="number" min="50" max="4000" value={llm.max_tokens ?? 500}
                  onChange={e => set("llm", { ...llm, max_tokens: Number(e.target.value) })} />
              </div>
            </div>
          </div>

          <div className="card">
            <h3>Derivación a asesor (handoff)</h3>
            <label className="muted" style={{ fontSize: 12 }}>Número WhatsApp del asesor</label>
            <input value={handoff.number ?? ""} onChange={e => set("handoff", { ...handoff, number: e.target.value })} />
            <label className="muted" style={{ fontSize: 12 }}>Palabras clave (separadas por coma)</label>
            <input value={(handoff.keywords ?? []).join(", ")}
              onChange={e => set("handoff", { ...handoff, keywords: e.target.value.split(",").map(s => s.trim()).filter(Boolean) })} />
            <label className="muted" style={{ fontSize: 12 }}>Mensaje de derivación (usa {"{number}"})</label>
            <textarea rows={2} style={{ width: "100%" }} value={handoff.message ?? ""}
              onChange={e => set("handoff", { ...handoff, message: e.target.value })} />
            <p className="muted" style={{ fontSize: 11, marginTop: 6 }}>Al derivar, la conversación se asigna automáticamente al asesor del panel con menos carga.</p>
          </div>

          <div className="card">
            <h3>Cotizador de remesas</h3>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}>
              <input type="checkbox" checked={!!quote.enabled}
                onChange={e => set("quote", { ...quote, enabled: e.target.checked })} />
              Activado (responde cotizaciones sin gastar LLM)
            </label>
            {quote.enabled && <>
              <label className="muted" style={{ fontSize: 12, marginTop: 8, display: "block" }}>Tasas oficiales por corredor</label>
              {liveRates.map(item => (
                <div className="kv" key={item.pair}>
                  <span style={{ fontFamily: "var(--mono)", fontSize: 12 }}>{item.pair}</span>
                  <b style={{ fontFamily: "var(--mono)" }}>{item.rate.toFixed(4)}</b>
                </div>
              ))}
              <p className="muted" style={{ fontSize: 11, marginTop: 8 }}>{ratesNote}. Tasas, comisiones y cupones son de solo lectura.</p>
            </>}
          </div>
        </div>
      )}
    </>
  );
}

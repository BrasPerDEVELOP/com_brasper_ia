"use client";
import { useState } from "react";
import { api, Me } from "@/lib/api";

/** Cambio de la propia contraseña. El servidor valida la actual, la longitud mínima y
 *  revoca las demás sesiones; aquí solo se comprueba que la confirmación coincida. */
export default function PasswordForm({ me, onChanged }: { me: Me; onChanged: (m: Me) => void }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  const first = !me.has_password;
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy) return;
    setErr(""); setOk(false);
    if (next !== confirm) { setErr("La confirmación no coincide"); return; }
    setBusy(true);
    try {
      const d = await api<{ user: Me }>("/api/me/password", { method: "POST", body: JSON.stringify({ current_password: current, new_password: next }) });
      setCurrent(""); setNext(""); setConfirm(""); setOk(true);
      onChanged(d.user);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }
  return (
    <form onSubmit={submit} style={{ display: "grid", gap: 10, maxWidth: 420 }}>
      <label className="fld">{first ? "Código de acceso vigente" : "Contraseña actual"}
        <input type="password" value={current} autoComplete="current-password" onChange={e => setCurrent(e.target.value)} />
      </label>
      <label className="fld">Nueva contraseña (mínimo 10 caracteres)
        <input type="password" value={next} autoComplete="new-password" minLength={10} maxLength={256} onChange={e => setNext(e.target.value)} />
      </label>
      <label className="fld">Repite la nueva contraseña
        <input type="password" value={confirm} autoComplete="new-password" onChange={e => setConfirm(e.target.value)} />
      </label>
      <button className="btn" type="submit" disabled={busy || !next || !confirm}>{busy ? "Guardando…" : "Cambiar contraseña"}</button>
      {err && <div className="err" role="alert">{err}</div>}
      {ok && <div role="status">Contraseña actualizada. Tus otras sesiones se cerraron.</div>}
    </form>
  );
}

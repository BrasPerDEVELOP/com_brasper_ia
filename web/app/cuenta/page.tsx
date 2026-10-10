"use client";
import { useMe } from "@/components/AppFrame";
import PasswordForm from "@/components/PasswordForm";

export default function Cuenta() {
  const me = useMe();
  if (!me) return null;
  return <>
    <h2>Mi cuenta</h2>
    <div className="card">
      <p><b>{me.name}</b> · {me.email} · rol <code>{me.role}</code></p>
      <h3>{me.has_password ? "Cambiar mi contraseña" : "Fijar mi contraseña"}</h3>
      {!me.has_password && <p className="usage-note">Aún entras con el código compartido. Fija una contraseña individual: escribe el código vigente como contraseña actual.</p>}
      <PasswordForm me={me} onChanged={() => window.location.reload()} />
    </div>
  </>;
}

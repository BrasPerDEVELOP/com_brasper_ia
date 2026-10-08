"use client";
import { useEffect } from "react";
import Icon from "../Icon";

export default function Lightbox({ url, name, onClose }: { url: string; name?: string; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);
  return (
    <div className="lightbox" onClick={onClose} role="dialog" aria-label={name || "Imagen"}>
      <div className="lb-acts" onClick={e => e.stopPropagation()}>
        <a className="ibtn" href={url} download={name || "imagen"} title="Descargar" aria-label="Descargar"><Icon name="download" size={18} /></a>
        <button className="ibtn" onClick={onClose} title="Cerrar (Esc)" aria-label="Cerrar"><Icon name="x" size={18} /></button>
      </div>
      <img src={url} alt={name || "imagen"} onClick={e => e.stopPropagation()} />
    </div>
  );
}

"use client";
import { useEffect, useState } from "react";
import { apiBlob, MediaRef } from "./api";

// Caché de adjuntos en memoria: el hilo se refresca cada pocos segundos y sin esto
// cada burbuja volvía a descargar su imagen. Un object URL por (provider, ref).
const cache = new Map<string, Promise<string>>();
const key = (m: MediaRef) => `${m.provider}:${m.ref}`;

export function mediaUrl(m: MediaRef): Promise<string> {
  const k = key(m);
  let p = cache.get(k);
  if (!p) {
    p = apiBlob(`/api/media?provider=${encodeURIComponent(m.provider)}&ref=${encodeURIComponent(m.ref)}`)
      .then(b => URL.createObjectURL(b));
    p.catch(() => cache.delete(k));
    cache.set(k, p);
  }
  return p;
}

export function useMediaUrl(m: MediaRef): { url: string; error: boolean } {
  const [url, setUrl] = useState("");
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    setUrl(""); setError(false);
    mediaUrl(m).then(u => { if (alive) setUrl(u); }).catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [m.provider, m.ref]); // eslint-disable-line react-hooks/exhaustive-deps
  return { url, error };
}

export const isImageMedia = (m: MediaRef) =>
  m.kind === "image" || m.kind === "sticker" || (m.mime || "").startsWith("image/");

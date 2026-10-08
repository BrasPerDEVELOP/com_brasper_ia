"use client";
import type { MediaRef } from "@/lib/api";
import { isImageMedia, useMediaUrl } from "@/lib/media";
import Icon from "../Icon";

const isAudioMedia = (m: MediaRef) => m.kind === "audio" || m.kind === "voice" || (m.mime || "").startsWith("audio/");

export default function MediaBubble({ media, onOpen }: { media: MediaRef; onOpen: (url: string, name?: string) => void }) {
  const { url, error } = useMediaUrl(media);
  const img = isImageMedia(media);
  const audio = isAudioMedia(media);
  if (error) return <div className="media-ph"><span><Icon name="alert" size={14} /> adjunto no disponible</span></div>;
  if (!url) return <div className={"media-ph sk"} style={img ? undefined : { height: 52, width: 220 }} aria-busy="true" />;
  if (img) {
    return (
      <img className="media-img" src={url} alt={media.name || media.caption || "imagen"} loading="lazy"
        onClick={() => onOpen(url, media.name || undefined)} />
    );
  }
  if (audio) {
    // Evidencia reproducible en el panel: el asesor escucha el audio original aunque
    // la transcripción haya fallado o sea ambigua.
    return (
      <div className="media-audio">
        <audio controls preload="metadata" src={url} aria-label="Audio del cliente" />
        <a className="ibtn" href={url} download={media.name || "audio.ogg"} title="Descargar audio" aria-label="Descargar audio"><Icon name="download" size={15} /></a>
      </div>
    );
  }
  const isPdf = (media.mime || "").includes("pdf") || /\.pdf$/i.test(media.name || "");
  return (
    <a className="media-file" href={url} download={media.name || "archivo"} title="Descargar">
      <span className="fi"><Icon name={isPdf ? "pdf" : "file"} size={18} /></span>
      <span style={{ minWidth: 0 }}>
        <span className="fn" style={{ display: "block" }}>{media.name || media.kind}</span>
        <span className="fm">{isPdf ? "PDF" : media.mime || media.kind} · descargar</span>
      </span>
    </a>
  );
}

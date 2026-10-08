import type { Message } from "@/lib/api";

/** Mensaje del hilo con estado local (envío optimista). */
export type LocalState = "pending" | "failed";
export interface LocalMessage extends Message {
  _local?: { id: string; state: LocalState; retry?: () => void; detail?: string };
}

/** Archivo elegido por el asesor, aún no enviado. */
export interface PendingFile {
  id: string;
  file: File;
  preview?: string;   // object URL para imágenes
  error?: string;     // validación local (tamaño, tipo)
}

export type InboxTab = "inbox" | "mine" | "queue" | "bot" | "closed";

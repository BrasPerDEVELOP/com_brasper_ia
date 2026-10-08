"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, can, qs, Advisor, Conversation, ConversationsResp, Note, QuickReply, ThreadResp } from "@/lib/api";
import { displayName, matches, type Lead } from "@/lib/format";
import { useMe } from "@/components/AppFrame";
import { useToast } from "@/components/Toast";
import ConversationList from "@/components/inbox/ConversationList";
import Thread from "@/components/inbox/Thread";
import LeadCard from "@/components/inbox/LeadCard";
import Lightbox from "@/components/inbox/Lightbox";
import { validateFile } from "@/components/inbox/Composer";
import type { InboxTab, LocalMessage, PendingFile } from "@/components/inbox/types";

const POLL_MS = 3000;          // pestaña visible: solo cambios (since / after)
const POLL_HIDDEN_MS = 15000;  // pestaña oculta
const FULL_EVERY_MS = 60000;   // recarga completa (detecta borrados)
const LIST_LIMIT = 300;
const SEEN_KEY = "brasper_seen";

const uid = () => Math.random().toString(36).slice(2, 10);
const nowIso = () => new Date().toISOString();
const msgKey = (m: LocalMessage) => `${m.created_at || ""}|${m.role}|${m.content}|${m.media?.ref || ""}`;

function loadSeen(): Record<string, number> {
  try { return JSON.parse(localStorage.getItem(SEEN_KEY) || "{}"); } catch { return {}; }
}

export default function Conversaciones() {
  const me = useMe();
  const { toast } = useToast();

  const [convs, setConvs] = useState<Conversation[]>([]);
  const [loadingList, setLoadingList] = useState(true);
  const [sel, setSel] = useState<string | null>(null);
  const [msgs, setMsgs] = useState<LocalMessage[]>([]);
  const [loadingThread, setLoadingThread] = useState(false);
  const [lead, setLead] = useState<Lead>({});
  const [notes, setNotes] = useState<Note[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [allTags, setAllTags] = useState<string[]>([]);
  const [tagFilter, setTagFilter] = useState<string | null>(null);
  const [channelFilter, setChannelFilter] = useState<string | null>(null);
  const [quickReplies, setQuickReplies] = useState<QuickReply[]>([]);
  const [advisors, setAdvisors] = useState<Advisor[]>([]);
  const [load, setLoad] = useState<Record<string, number>>({});
  const [tab, setTab] = useState<InboxTab>("inbox");
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const [pending, setPending] = useState<PendingFile[]>([]);
  const [showProfile, setShowProfile] = useState(false);
  const [mobileView, setMobileView] = useState<"list" | "thread">("list");
  const [lightbox, setLightbox] = useState<{ url: string; name?: string } | null>(null);
  const [seen, setSeen] = useState<Record<string, number>>({});
  const [now, setNow] = useState(() => Date.now());
  const searchRef = useRef<HTMLInputElement>(null);
  const selRef = useRef<string | null>(null);
  const sinceRef = useRef<string | null>(null);     // máximo updated_at visto (polling incremental)
  const lastFullRef = useRef(0);
  const lastMsgTsRef = useRef<string | null>(null); // created_at del último mensaje del servidor
  selRef.current = sel;

  // ---------- carga de lista: completa o incremental ----------
  const mergeConvs = useCallback((incoming: Conversation[], full: boolean) => {
    setConvs(prev => {
      if (full) return incoming;
      if (!incoming.length) return prev;
      const map = new Map(prev.map(c => [c.id, c]));
      for (const c of incoming) map.set(c.id, c);
      return Array.from(map.values()).sort((a, b) => (a.updated_at < b.updated_at ? 1 : a.updated_at > b.updated_at ? -1 : 0));
    });
    for (const c of incoming) if (!sinceRef.current || c.updated_at > sinceRef.current) sinceRef.current = c.updated_at;
  }, []);

  const loadConvs = useCallback(async (force = false) => {
    const full = force || !sinceRef.current || Date.now() - lastFullRef.current > FULL_EVERY_MS;
    try {
      const d = await api<ConversationsResp>(`/api/conversations${qs({ limit: LIST_LIMIT, since: full ? undefined : sinceRef.current })}`);
      if (full) lastFullRef.current = Date.now();
      mergeConvs(d.conversations, full);
    } catch { /* se mantiene lo que había */ }
    finally { setLoadingList(false); }
  }, [mergeConvs]);

  // ---------- hilo: completo al abrir, incremental después ----------
  const loadThread = useCallback(async (id: string, initial = false) => {
    if (initial) { setLoadingThread(true); lastMsgTsRef.current = null; }
    try {
      const after = initial ? undefined : lastMsgTsRef.current;
      const d = await api<ThreadResp>(`/api/conversations/${id}${qs({ after })}`);
      if (selRef.current !== id) return;
      const server = d.messages as LocalMessage[];
      if (server.length) lastMsgTsRef.current = server[server.length - 1].created_at || lastMsgTsRef.current;
      setMsgs(prev => {
        const locals = prev.filter(m => !!m._local); // pendientes y fallidos aún no están en el servidor
        if (!d.partial) return [...server, ...locals];
        if (!server.length) return prev;
        const known = new Set(prev.filter(m => !m._local).map(msgKey));
        const fresh = server.filter(m => !known.has(msgKey(m)));
        if (!fresh.length) return prev;
        return [...prev.filter(m => !m._local), ...fresh, ...locals];
      });
      if (d.lead) setLead(d.lead);
      if (d.notes) setNotes(d.notes);
      if (d.tags) setTags(d.tags);
    } catch { if (initial) { setMsgs([]); setLead({}); setNotes([]); setTags([]); } }
    finally { if (initial) setLoadingThread(false); }
  }, []);

  useEffect(() => {
    setSeen(loadSeen());
    loadConvs(true);
    api<{ quick_replies: QuickReply[] }>("/api/quick-replies").then(d => setQuickReplies(d.quick_replies)).catch(() => {});
    api<{ advisors: Advisor[]; load: Record<string, number> }>("/api/advisors").then(d => { setAdvisors(d.advisors); setLoad(d.load || {}); }).catch(() => {});
    api<{ tags: { tag: string; count: number }[] }>("/api/tags").then(d => setAllTags(d.tags.map(t => t.tag))).catch(() => {});
  }, [loadConvs]);

  // Polling incremental (más lento con la pestaña oculta) + reloj para tiempos relativos.
  useEffect(() => {
    let t: number;
    const tick = () => {
      setNow(Date.now());
      loadConvs();
      if (selRef.current) loadThread(selRef.current);
      t = window.setTimeout(tick, document.hidden ? POLL_HIDDEN_MS : POLL_MS);
    };
    t = window.setTimeout(tick, POLL_MS);
    const onVis = () => { if (!document.hidden) { clearTimeout(t); tick(); } };
    document.addEventListener("visibilitychange", onVis);
    return () => { clearTimeout(t); document.removeEventListener("visibilitychange", onVis); };
  }, [loadConvs, loadThread]);

  // ---------- selección ----------
  const markSeen = useCallback((c: Conversation) => {
    setSeen(s => {
      if (s[c.id] === c.message_count) return s;
      const n = { ...s, [c.id]: c.message_count };
      try { localStorage.setItem(SEEN_KEY, JSON.stringify(n)); } catch { /* noop */ }
      return n;
    });
  }, []);

  const open = useCallback((id: string) => {
    if (id !== selRef.current) { setMsgs([]); setLead({}); setNotes([]); setTags([]); setPending([]); }
    setSel(id);
    setMobileView("thread");
    loadThread(id, true);
  }, [loadThread]);

  const selConv = useMemo(() => convs.find(c => c.id === sel) || null, [convs, sel]);
  useEffect(() => { if (selConv) markSeen(selConv); }, [selConv, markSeen]);

  // ---------- filtros ----------
  const myEmail = me?.email || "";
  const byTab = useCallback((c: Conversation, t: InboxTab) => {
    switch (t) {
      case "inbox": return c.status !== "closed";
      case "mine": return c.status !== "closed" && !!c.assigned_to && c.assigned_to === myEmail;
      case "queue": return c.status === "handoff" && !c.assigned_to;
      case "bot": return c.status === "active";
      case "closed": return c.status === "closed";
    }
  }, [myEmail]);

  const counts = useMemo(() => {
    const r: Record<InboxTab, number> = { inbox: 0, mine: 0, queue: 0, bot: 0, closed: 0 };
    for (const c of convs) (Object.keys(r) as InboxTab[]).forEach(t => { if (byTab(c, t)) r[t]++; });
    return r;
  }, [convs, byTab]);

  const visible = useMemo(() => {
    const q = query.trim();
    return convs.filter(c => byTab(c, tab) && matches(c, q, c.id === sel ? lead : null)
      && (!channelFilter || c.channel === channelFilter)
      && (!tagFilter || (c.tags || []).includes(tagFilter)));
  }, [convs, tab, query, byTab, sel, lead, channelFilter, tagFilter]);

  // No leídos: mensajes nuevos desde la última vez que se abrió, solo si el último habló el cliente.
  const unread = useMemo(() => {
    const r: Record<string, number> = {};
    for (const c of convs) {
      if (c.status === "closed" || c.last_role !== "user") continue;
      const s = seen[c.id];
      if (s === undefined) r[c.id] = Math.min(c.message_count, 9);
      else if (c.message_count > s) r[c.id] = c.message_count - s;
    }
    return r;
  }, [convs, seen]);

  // ---------- acciones ----------
  const refresh = useCallback(async (id: string) => { await Promise.all([loadThread(id), loadConvs()]); }, [loadThread, loadConvs]);

  function pushLocal(m: LocalMessage) { setMsgs(prev => [...prev, m]); }
  function patchLocal(id: string, patch: Partial<LocalMessage["_local"]> & { state: "pending" | "failed" }) {
    setMsgs(prev => prev.map(m => (m._local?.id === id ? { ...m, _local: { ...m._local!, ...patch } } : m)));
  }
  function dropLocal(id: string) { setMsgs(prev => prev.filter(m => m._local?.id !== id)); }

  async function sendText(text: string): Promise<boolean> {
    if (!sel) return false;
    const files = pending.filter(p => !p.error);
    if (files.length) return sendFiles(files, text);
    if (!text) return false;
    const id = uid();
    const conv = sel;
    const attempt = async () => {
      patchLocal(id, { state: "pending" });
      try {
        const r = await api<{ delivery?: { sent?: boolean; reason?: string } }>(`/api/conversations/${conv}/reply`, {
          method: "POST", body: JSON.stringify({ text }),
        });
        if (r.delivery && r.delivery.sent === false) toast(`Guardado, pero no se entregó: ${r.delivery.reason || "canal sin envío"}`, "warn");
        dropLocal(id);
        await refresh(conv);
      } catch (e) {
        patchLocal(id, { state: "failed", detail: (e as Error).message, retry: attempt });
      }
    };
    pushLocal({ role: "assistant", sender: "agent", agent_email: myEmail, content: text, created_at: nowIso(), _local: { id, state: "pending" } });
    attempt();
    return true;
  }

  async function sendFiles(files: PendingFile[], caption: string): Promise<boolean> {
    if (!sel) return false;
    const conv = sel;
    setBusy(true);
    setProgress({ done: 0, total: files.length });
    const failures: string[] = [];
    for (let i = 0; i < files.length; i++) {
      const p = files[i];
      const fd = new FormData();
      fd.append("file", p.file);
      if (i === 0 && caption) fd.append("caption", caption);
      try {
        const r = await api<{ delivery?: { sent?: boolean; detail?: string; reason?: string } }>(`/api/conversations/${conv}/upload`, { method: "POST", body: fd });
        if (r.delivery && r.delivery.sent === false) failures.push(`${p.file.name}: ${r.delivery.detail || r.delivery.reason || "no entregado"}`);
        else setPending(prev => prev.filter(x => x.id !== p.id));
      } catch (e) { failures.push(`${p.file.name}: ${(e as Error).message}`); }
      setProgress({ done: i + 1, total: files.length });
    }
    setProgress(null); setBusy(false);
    await refresh(conv);
    if (failures.length) {
      toast(`Enviados ${files.length - failures.length} de ${files.length}.\n${failures.join("\n")}`, "err");
      setPending(prev => prev.map(x => failures.some(f => f.startsWith(x.file.name + ":")) ? { ...x, error: "No enviado" } : x));
      return false;
    }
    toast(files.length === 1 ? "Archivo enviado" : `${files.length} archivos enviados`, "ok");
    setPending(prev => prev.filter(x => x.error)); // conserva solo los inválidos para que el asesor los vea
    return true;
  }

  async function sendUrl(url: string, caption: string): Promise<boolean> {
    if (!sel) return false;
    const conv = sel;
    setBusy(true);
    try {
      const r = await api<{ delivery?: { sent?: boolean; reason?: string } }>(`/api/conversations/${conv}/send-image`, {
        method: "POST", body: JSON.stringify({ image_url: url, caption: caption || undefined }),
      });
      if (r.delivery && r.delivery.sent === false) toast(`No se entregó: ${r.delivery.reason || "canal sin envío"}`, "warn");
      else toast("Imagen enviada", "ok");
      await refresh(conv);
      return true;
    } catch (e) { toast((e as Error).message, "err"); return false; }
    finally { setBusy(false); }
  }

  async function sendNote(text: string): Promise<boolean> {
    if (!sel || !text) return false;
    try {
      const r = await api<{ note: Note }>(`/api/conversations/${sel}/notes`, { method: "POST", body: JSON.stringify({ text }) });
      setNotes(prev => [r.note, ...prev]);
      toast("Nota guardada (solo la ve el equipo)", "ok");
      return true;
    } catch (e) { toast((e as Error).message, "err"); return false; }
  }

  const setStatus = useCallback(async (status: "handoff" | "active" | "closed") => {
    const conv = selRef.current; if (!conv) return;
    setBusy(true);
    try {
      await api(`/api/conversations/${conv}/status`, { method: "POST", body: JSON.stringify({ status }) });
      toast(status === "handoff" ? "Conversación tomada. El bot queda en pausa." : status === "active" ? "Devuelta al bot." : "Conversación cerrada.", "ok");
      await refresh(conv);
    } catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }, [refresh, toast]);

  async function assign(email: string | null) {
    if (!sel) return;
    setBusy(true);
    try {
      await api(`/api/conversations/${sel}/assign`, { method: "POST", body: JSON.stringify({ email }) });
      toast(email ? `Asignada a ${email.split("@")[0]}` : "Conversación liberada", "ok");
      await loadConvs(true);
      api<{ advisors: Advisor[]; load: Record<string, number> }>("/api/advisors").then(d => setLoad(d.load || {})).catch(() => {});
    } catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }

  async function remove() {
    if (!selConv) return;
    setBusy(true);
    try {
      await api(`/api/conversations/${selConv.id}${qs({ expected_user_ref: selConv.user_ref })}`, { method: "DELETE" });
      toast("Conversación eliminada", "ok");
      setSel(null); setMsgs([]); setLead({}); setNotes([]); setMobileView("list"); setShowProfile(false);
      await loadConvs(true);
    } catch (e) { toast((e as Error).message, "err"); }
    setBusy(false);
  }

  async function addTag(tag: string) {
    if (!sel) return;
    try {
      const r = await api<{ tags: string[] }>(`/api/conversations/${sel}/tags`, { method: "POST", body: JSON.stringify({ tag }) });
      setTags(r.tags);
      setAllTags(prev => (prev.includes(tag) ? prev : [...prev, tag].sort()));
      setConvs(prev => prev.map(c => (c.id === sel ? { ...c, tags: r.tags } : c)));
    } catch (e) { toast((e as Error).message, "err"); }
  }
  async function removeTag(tag: string) {
    if (!sel) return;
    try {
      const r = await api<{ tags: string[] }>(`/api/conversations/${sel}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });
      setTags(r.tags);
      setConvs(prev => prev.map(c => (c.id === sel ? { ...c, tags: r.tags } : c)));
    } catch (e) { toast((e as Error).message, "err"); }
  }

  const addFiles = useCallback((list: FileList | File[]) => {
    if (!selConv) return;
    const arr = Array.from(list);
    setPending(prev => {
      const next = [...prev];
      for (const f of arr) {
        if (next.length >= 10) { toast("Máximo 10 archivos por envío", "warn"); break; }
        const error = validateFile(f, selConv.channel);
        next.push({ id: uid(), file: f, preview: f.type.startsWith("image/") ? URL.createObjectURL(f) : undefined, error });
      }
      return next;
    });
  }, [selConv, toast]);

  const removeFile = useCallback((id: string) => {
    setPending(prev => { const p = prev.find(x => x.id === id); if (p?.preview) URL.revokeObjectURL(p.preview); return prev.filter(x => x.id !== id); });
  }, []);

  // ---------- atajos ----------
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tgt = e.target as HTMLElement | null;
      const typing = !!tgt && (tgt.tagName === "INPUT" || tgt.tagName === "TEXTAREA" || tgt.tagName === "SELECT" || tgt.isContentEditable);
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); searchRef.current?.focus(); searchRef.current?.select(); return; }
      if (e.key === "Escape") {
        if (lightbox) { setLightbox(null); return; }
        if (showProfile) { setShowProfile(false); return; }
        if (typing && tgt === searchRef.current) { setQuery(""); tgt.blur(); return; }
      }
      if (typing && tgt !== searchRef.current) return;
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        if (!visible.length) return;
        e.preventDefault();
        const i = visible.findIndex(c => c.id === sel);
        const n = e.key === "ArrowDown" ? Math.min(visible.length - 1, i + 1) : Math.max(0, i - 1);
        if (visible[n] && visible[n].id !== sel) open(visible[n].id);
        return;
      }
      if (typing) return; // en la búsqueda, las letras son texto
      const c = selConv; if (!c || busy) return;
      const k = e.key.toLowerCase();
      if (k === "t" && c.status !== "handoff") setStatus("handoff");
      else if (k === "r" && c.status === "handoff") setStatus("active");
      else if (k === "e" && c.status !== "closed") setStatus("closed");
      else if (k === "i") setShowProfile(s => !s);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [visible, sel, open, lightbox, showProfile, selConv, busy, setStatus]);

  const inboxCls = ["inbox", !selConv ? "no-profile" : "", showProfile && selConv ? "show-profile" : "", `v-${mobileView}`].filter(Boolean).join(" ");

  return (
    <>
      <div className={inboxCls}>
        <ConversationList convs={visible} counts={counts} tab={tab} onTab={setTab} query={query} onQuery={setQuery}
          sel={sel} unread={unread} loading={loadingList} now={now} onOpen={open} searchRef={searchRef}
          allTags={allTags} tagFilter={tagFilter} onTagFilter={setTagFilter} channelFilter={channelFilter} onChannelFilter={setChannelFilter} />
        <Thread c={selConv} lead={lead} msgs={msgs} loading={loadingThread} busy={busy} progress={progress} pending={pending}
          notesCount={notes.length} quickReplies={quickReplies}
          showProfile={showProfile} onToggleProfile={() => setShowProfile(s => !s)} onBack={() => setMobileView("list")}
          onStatus={setStatus} onAddFiles={addFiles} onRemoveFile={removeFile} onSend={sendText} onSendUrl={sendUrl} onSendNote={sendNote}
          onOpenMedia={(url, name) => setLightbox({ url, name })} />
        {selConv && (
          <LeadCard c={selConv} lead={lead} notes={notes} tags={tags} advisors={advisors} load={load}
            canAssign={can(me, "conversations:write")} canDelete={can(me, "tenants:write")} busy={busy}
            onClose={() => setShowProfile(false)} onAssign={assign} onDelete={remove} onAddTag={addTag} onRemoveTag={removeTag} />
        )}
      </div>
      {lightbox && <Lightbox url={lightbox.url} name={lightbox.name || (selConv ? displayName(selConv, lead) : undefined)} onClose={() => setLightbox(null)} />}
    </>
  );
}

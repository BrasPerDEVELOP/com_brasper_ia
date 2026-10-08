"""Evaluaciones de escenarios ES/PT del bot Brasper — deterministas, sin LLM real ni red.

Ejecutar:
    cd backend && ../.venv/bin/python tests/evals/run.py            # macOS / Linux
    cd backend && ..\\.venv\\Scripts\\python.exe tests\\evals\\run.py   # Windows
Opciones: --only <id-substring> · --verbose

Lee `tests/evals/scenarios.json` (50+ escenarios: cotizar, cambiar monto, retomar,
documentos, audio, estado, asesor, caída de API, webhook duplicado, timeout tras
escritura, intento de cambiar instrucciones) y los ejecuta contra el grafo real con:
  - DB SQLite temporal y copia temporal de tenants.json (hermético)
  - LLM stub (texto fijo) para que cualquier número en la salida venga de herramientas
  - API Brasper apagada salvo en escenarios `setup: brasper_api_down` (simulada caída)
Un escenario pasa si TODAS sus expectativas se cumplen. sys.exit(1) si alguno falla.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ["DATABASE_URL"] = ""
os.environ["REDIS_URL"] = ""
os.environ["APP_ENV"] = "development"
os.environ["WA_PHONE_NUMBER_ID_BRASPER"] = "PNID_EVAL_1"

_TMP = Path(tempfile.mkdtemp(prefix="evals_"))

from core import tenants as T  # noqa: E402

_TMP_CONFIG = _TMP / "tenants.json"
shutil.copy2(T.CONFIG_PATH, _TMP_CONFIG)
T.CONFIG_PATH = _TMP_CONFIG
T.reload_config()

from core import db  # noqa: E402

db.DB_PATH = _TMP / "evals.db"
db.init_db()

from core import audio_flow, auth, brasper_api, engine, idempotency, llm, tool_contracts, whatsapp  # noqa: E402

STUB_TEXT = "[respuesta simulada]"


async def _stub_chat(tenant, messages):
    return {"content": STUB_TEXT, "provider": "stub", "model": "stub-model",
            "tokens_in": 10, "tokens_out": 5, "cost_usd": 0.0}


llm.chat = _stub_chat
auth.ensure_seed()
# Sin red: la API Brasper queda apagada (cotiza con tasas de config) salvo en `setup: brasper_api_down`.
brasper_api.enabled = lambda t: False
brasper_api._fetch = lambda url: None

SCENARIOS = Path(__file__).with_name("scenarios.json")
_NUM_RE = re.compile(r"\d+(?:[.,]\d+)?")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _check_expect(exp: dict, out: dict, user_text: str, errors: list[str]) -> None:
    resp = (out.get("response") or "")
    low = resp.lower()
    if "flow" in exp and out.get("flow") != exp["flow"]:
        errors.append(f"flow={out.get('flow')!r} esperado {exp['flow']!r}")
    if "handoff" in exp and bool(out.get("handoff")) != bool(exp["handoff"]):
        errors.append(f"handoff={out.get('handoff')} esperado {exp['handoff']}")
    if exp.get("usage_none") and out.get("usage") is not None:
        errors.append("usage debía ser None (sin LLM)")
    if exp.get("usage_present") and out.get("usage") is None:
        errors.append("usage debía existir (LLM)")
    for frag in exp.get("contains", []):
        if frag.lower() not in low.replace(",", ""):
            errors.append(f"falta «{frag}» en la respuesta")
    for frag in exp.get("not_contains", []):
        if frag.lower() in low:
            errors.append(f"no debía contener «{frag}»")
    if exp.get("no_new_numbers"):
        # Ningún número en la respuesta que no esté en el texto del usuario (anti-invención).
        allowed = set(_NUM_RE.findall(user_text))
        # Los ejemplos de uso ("Cotizar 500 PEN a BRL") son texto fijo del bot, no datos inventados.
        scan = re.sub(r"\*?Cotizar \d+ [A-Z]{3} a [A-Z]{3}\*?", "", resp)
        found = {n for n in _NUM_RE.findall(scan) if n not in allowed and not re.fullmatch(r"20\d\d(-\d\d)*", n)}
        if found:
            errors.append(f"números no respaldados: {sorted(found)}")
    if "status" in exp:
        st = db.conversation_status(out["conversation_id"])
        if st != exp["status"]:
            errors.append(f"status={st!r} esperado {exp['status']!r}")
    if exp.get("assigned") is True and not (db.get_conversation(out["conversation_id"]) or {}).get("assigned_to"):
        errors.append("debía quedar asignada a un asesor")
    if "handoff_reason" in exp:
        h = (db.get_lead_data(out["conversation_id"]) or {}).get("handoff") or {}
        if h.get("reason") != exp["handoff_reason"]:
            errors.append(f"handoff.reason={h.get('reason')!r} esperado {exp['handoff_reason']!r}")


class _ApiDown:
    def __enter__(self):
        self.saved = (brasper_api.enabled, brasper_api._fetch)
        brasper_api.enabled = lambda t: True
        brasper_api._fetch = lambda url: None
        return self

    def __exit__(self, *a):
        brasper_api.enabled, brasper_api._fetch = self.saved


def run_scenario(sc: dict, verbose: bool = False) -> list[str]:
    errors: list[str] = []
    kind = sc.get("kind", "chat")
    user_ref = sc.get("user_ref") or f"eval:{sc['id']}"
    cid = None
    ctx = _ApiDown() if sc.get("setup") == "brasper_api_down" else None
    if ctx:
        ctx.__enter__()
    try:
        if kind == "chat":
            for i, step in enumerate(sc["steps"]):
                out = _run(engine.handle_message(user_ref, step["user"], channel=sc.get("channel", "webchat"),
                                                 conversation_id=cid if step.get("same_conversation", True) else None))
                cid = out["conversation_id"]
                errs: list[str] = []
                _check_expect(step.get("expect", {}), out, step["user"], errs)
                if verbose:
                    print(f"    [{i + 1}] {step['user']!r} -> flow={out.get('flow')} handoff={out.get('handoff')} :: {out.get('response', '')[:90]!r}")
                errors += [f"paso {i + 1}: {e}" for e in errs]
        elif kind == "audio":
            sent: list[str] = []

            async def _send(text):
                sent.append(text)
                return {"ok": True}

            media = {"provider": "telegram", "kind": "voice", "ref": f"ref-{sc['id']}", "mime": "audio/ogg"}
            for i, step in enumerate(sc["steps"]):
                out = _run(audio_flow.process_transcript(channel="telegram", user_ref=user_ref, text=step["transcript"],
                                                         media=media, send=_send, conversation_id=cid))
                cid = out["conversation_id"]
                exp = step.get("expect", {})
                errs: list[str] = []
                if "ambiguous" in exp and bool(out.get("ambiguous")) != bool(exp["ambiguous"]):
                    errs.append(f"ambiguous={out.get('ambiguous')} esperado {exp['ambiguous']}")
                reply = sent[-1] if sent else ""
                fake_out = {**out, "response": reply}
                _check_expect({k: v for k, v in exp.items() if k != "ambiguous"}, fake_out, step["transcript"], errs)
                msgs = db.get_messages(cid)
                if not any(m.get("media", {}) and m["media"].get("ref") == media["ref"] for m in msgs if m.get("media")):
                    errs.append("la evidencia (audio) no quedó guardada")
                if verbose:
                    print(f"    [{i + 1}] audio {step['transcript']!r} -> ambiguous={out.get('ambiguous')} :: {reply[:90]!r}")
                errors += [f"paso {i + 1}: {e}" for e in errs]
        elif kind == "webhook":
            from fastapi.testclient import TestClient
            from main import app
            client = TestClient(app)
            sent: list = []

            async def _fake_send(to, text, connection=None, **kw):
                sent.append(text)
                return {"sent": True}

            old = whatsapp.send_text
            whatsapp.send_text = _fake_send
            try:
                body = {"object": "whatsapp_business_account", "entry": [{"changes": [{"field": "messages", "value": {
                    "metadata": {"phone_number_id": "PNID_EVAL_1"},
                    "contacts": [{"profile": {"name": "Eval"}, "wa_id": sc["from"]}],
                    "messages": [{"from": sc["from"], "id": sc["message_id"], "type": "text", "text": {"body": sc["text"]}}]}}]}]}
                r1 = client.post("/webhook", json=body).json()["results"][0]
                r2 = client.post("/webhook", json=body).json()["results"][0]
                if not r1.get("sent"):
                    errors.append(f"primer webhook no respondió: {r1}")
                if r2.get("duplicate") is not True:
                    errors.append(f"segundo webhook debía marcarse duplicado: {r2}")
                if len(sent) != 1:
                    errors.append(f"debía enviarse exactamente 1 respuesta, se enviaron {len(sent)}")
            finally:
                whatsapp.send_text = old
        elif kind == "tool":
            spec = sc["tool"]
            calls: list = []

            def _fn(**kw):
                calls.append(kw)
                if spec.get("sleep"):
                    time.sleep(spec["sleep"])
                return spec.get("returns")

            key = idempotency.make_key("eval", sc["id"]) if spec.get("idempotent") else None
            r1 = tool_contracts.run(spec["name"], spec.get("inputs", {}), _fn, idempotency_key=key)
            r2 = tool_contracts.run(spec["name"], spec.get("inputs", {}), _fn, idempotency_key=key) if spec.get("twice") else None
            exp = sc.get("expect", {})
            if "error_code" in exp and r1.get("error_code") != exp["error_code"]:
                errors.append(f"error_code={r1.get('error_code')!r} esperado {exp['error_code']!r}")
            if exp.get("ok") is True and not r1.get("ok"):
                errors.append(f"debía ser ok: {r1}")
            if "calls" in exp and len(calls) != exp["calls"]:
                errors.append(f"llamadas={len(calls)} esperado {exp['calls']}")
            if exp.get("replayed") and not (r2 and r2.get("replayed")):
                errors.append(f"la repetición debía reproducir el resultado: {r2}")
        else:
            errors.append(f"kind desconocido: {kind}")
    except Exception as exc:  # noqa: BLE001 - el escenario falla, la suite sigue
        errors.append(f"{type(exc).__name__}: {exc}")
    finally:
        if ctx:
            ctx.__exit__(None, None, None)
    return errors


def main() -> int:
    args = sys.argv[1:]
    verbose = "--verbose" in args
    only = args[args.index("--only") + 1] if "--only" in args else None
    data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    scenarios = [s for s in data["scenarios"] if not only or only in s["id"]]
    failed = 0
    by_cat: dict[str, list[int]] = {}
    for sc in scenarios:
        errs = run_scenario(sc, verbose)
        ok = not errs
        by_cat.setdefault(sc.get("category", "otros"), [0, 0])
        by_cat[sc["category"]][0 if ok else 1] += 1
        print(f"[{'PASS' if ok else 'FAIL'}] {sc['id']} ({sc.get('lang', 'es')}, {sc.get('category')})" + ("" if ok else "  ->  " + " | ".join(errs)))
        failed += 0 if ok else 1
    print("-" * 60)
    for cat, (p, f) in sorted(by_cat.items()):
        print(f"  {cat:<22} PASS {p:>3}  FAIL {f:>3}")
    print(f"Total: {len(scenarios)}  PASS: {len(scenarios) - failed}  FAIL: {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

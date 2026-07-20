"""Smoke E2E REAL contra un backend corriendo (Postgres + LLM reales).

A diferencia de run_checks.py (hermético, sin red), esto golpea el servidor vivo:
    cd backend && ../.venv/bin/python tests/e2e_smoke.py [--base http://localhost:8002]

Requiere: backend arriba, login demo o PANEL_LOGIN_CODE, y (para el paso LLM)
una API key real — ese paso gasta ~US$0.0002 y puede saltarse con --skip-llm.
"""
from __future__ import annotations

import argparse
import sys

import httpx

RESULTS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    RESULTS.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  -> {detail}" if detail and not ok else ""))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8002")
    ap.add_argument("--email", default="owner@agencia.com")
    ap.add_argument("--code", default="demo1234")
    ap.add_argument("--tenant", default="brasper")
    ap.add_argument("--skip-llm", action="store_true", help="no gastar LLM real")
    args = ap.parse_args()
    c = httpx.Client(base_url=args.base, timeout=60)

    # 1. Salud
    r = c.get("/health")
    h = r.json()
    check("health responde", r.status_code in (200, 503), f"{r.status_code}")
    check("base de datos OK", h.get("db", {}).get("ok") is True, str(h.get("db")))

    # 2. Login
    r = c.post("/api/login", json={"email": args.email, "code": args.code})
    check("login", r.status_code == 200, r.text[:120])
    if r.status_code != 200:
        return _report()
    headers = {"X-Auth-Token": r.json()["token"]}

    # 3. Seguridad: token demo no debe servir en producción
    if h.get("env") == "production":
        r = c.get("/api/me", headers={"X-Auth-Token": "demo-owner"})
        check("token demo rechazado en produccion", r.status_code == 401, f"{r.status_code}")

    # 4. Tenants visibles
    r = c.get("/api/tenants", headers=headers)
    ids = [t["id"] for t in r.json().get("tenants", [])]
    check("tenant objetivo visible", args.tenant in ids, str(ids))

    # 5. Cotización determinista (sin costo LLM). Nota: con la API de Brasper activa
    # la tasa es EN VIVO, así que no se valida un monto fijo, sino la estructura.
    r = c.post(f"/api/{args.tenant}/chat", headers=headers,
               json={"message": "Cotizar 500 PEN a BRL", "user_ref": "e2e-smoke"})
    d = r.json() if r.status_code == 200 else {}
    resp = d.get("response", "")
    quote_ok = (r.status_code == 200 and "Cotización" in resp and "recibes" in resp
                and "BRL" in resp and "500.00 PEN" in resp)
    check("cotizador responde con montos", quote_ok, d.get("response", r.text)[:140])
    check("cotizador no gasta LLM", r.status_code == 200 and d.get("usage") is None,
          str(d.get("usage")))

    # 6. Handoff + derivación a asesor
    r = c.post(f"/api/{args.tenant}/chat", headers=headers,
               json={"message": "quiero hablar con un asesor", "user_ref": "e2e-smoke-handoff"})
    check("handoff responde", r.status_code == 200 and r.json().get("handoff") is True, r.text[:120])
    r = c.get(f"/api/{args.tenant}/conversations", headers=headers)
    conv = next((x for x in r.json().get("conversations", [])
                 if x["user_ref"] == "e2e-smoke-handoff"), {})
    check("conversacion derivada/asignada", conv.get("status") == "handoff",
          f"status={conv.get('status')} asignado={conv.get('assigned_to')}")

    # 7. LLM real (opt-out con --skip-llm; cuesta centavos de centavo)
    if not args.skip_llm:
        r = c.post(f"/api/{args.tenant}/chat", headers=headers,
                   json={"message": "hola, en que me ayudas?", "user_ref": "e2e-smoke-llm"})
        d = r.json() if r.status_code == 200 else {}
        check("LLM real responde", r.status_code == 200 and bool(d.get("response")), r.text[:140])
        check("LLM real mide tokens/costo", bool(d.get("usage", {}) or {}), str(d.get("usage")))

    # 8. Operación: usage diario, export, dead-letter, alerts
    for path, name in (("/api/ops/usage-daily", "usage-daily"),
                       (f"/api/{args.tenant}/export?limit=3", "export conversaciones"),
                       ("/api/ops/dead-letter", "dead-letter"),
                       ("/api/ops/alerts", "alerts")):
        r = c.get(path, headers=headers)
        check(f"endpoint {name}", r.status_code == 200, f"{r.status_code} {r.text[:80]}")

    return _report()


def _report() -> int:
    failed = sum(1 for _, ok, _ in RESULTS if not ok)
    print("-" * 56)
    print(f"E2E SMOKE — total {len(RESULTS)}  PASS {len(RESULTS) - failed}  FAIL {failed}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

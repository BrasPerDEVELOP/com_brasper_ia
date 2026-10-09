"""Read-only official status; private operations require trusted channel identity."""
import re

from . import brasper_api, db, features, identity_link, lead_onboarding, tenants, tool_contracts

LABELS = {
    "pending": ("pendiente", "pendente"),
    "verification": ("en verificación", "em verificação"),
    "verified": ("verificada; aún no completada", "verificada; ainda não concluída"),
    "checked": ("verificada; aún no completada", "verificada; ainda não concluída"),
    "completed": ("completada", "concluída"),
    "failed": ("fallida", "falhou"),
}


_REFERENCE = re.compile(r"\b(?:[A-Za-z]x[A-Za-z]-\d{1,20}|[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12})\b")


def _phone_run(lead, phone, reference):
    args = {"user_id": lead["brasper_user_id"], "code_phone": phone[0], "phone": phone[1]}
    if reference:
        args["reference"] = reference
    return tool_contracts.run("status.lookup", args,
                              lambda **kw: brasper_api.operation_status(tenants.get_config(), **kw))


def _linked_run(cid, link, reference):
    args = {k: link[k] for k in ("user_id", "grant", "channel", "subject")}
    if reference:
        args["reference"] = reference
    run = tool_contracts.run("status.linked", args,
                             lambda **kw: brasper_api.linked_operations(tenants.get_config(), **kw))
    result = run.get("data") if run.get("ok") else None
    # La API ya no reconoce el grant (vencido, revocado o cuenta inactiva): se olvida aquí también.
    if isinstance(result, dict) and result.get("status") == 401:
        identity_link.revoke(cid)
    return run


def lookup(cid, channel, user_ref, text, language):
    if not features.enabled("operation_status"):
        return None
    lead = db.get_lead_data(cid)
    phone = lead_onboarding.phone_from_channel(channel, user_ref)
    match = _REFERENCE.search(text)
    reference = match.group() if match else ""
    if (phone and lead.get("identity_source") == "channel_phone_match"
            and phone == (lead.get("codigo_telefono"), str(lead.get("telefono") or ""))
            and lead.get("brasper_user_id")):
        run = _phone_run(lead, phone, reference)
    else:
        # Sin teléfono verificado por el canal: solo un grant emitido desde la cuenta del cliente.
        link = identity_link.grant_for(cid, channel, user_ref)
        if link is None:
            return None
        run = _linked_run(cid, link, reference)
    result = run.get("data") if run.get("ok") else None
    if not isinstance(result, dict) or not result.get("ok"):
        return None
    body = result.get("data")
    items = body.get("data") if isinstance(body, dict) else None
    if not isinstance(items, list) or len(items) > 5:
        return None
    for item in items:
        if (not isinstance(item, dict) or item.get("status") not in LABELS
                or not isinstance(item.get("code"), str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", item["code"])):
            return None
    pt = language == "pt"
    if not items:
        return ("Não encontrei operações para esta consulta no seu perfil. Posso pedir ajuda a um atendente."
                if pt else "No encontré operaciones para esta consulta en tu perfil. Puedo pedir ayuda a un asesor.")
    title = "Estado consultado agora na Brasper:" if pt else "Estado consultado ahora en Brasper:"
    return title + "\n" + "\n".join(f"• {item['code']}: {LABELS[item['status']][int(pt)]}" for item in items)

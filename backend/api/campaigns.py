"""Administración de campañas en la plataforma IA (persistencia propia, sin proxy financiero).

Crear, editar, publicar y desactivar: `tenants:write`. Reservar, consumir o liberar un
beneficio de una conversación: `conversations:write` con alcance sobre esa conversación.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from core import auth, campaigns, cases, db

router = APIRouter(prefix="/api/admin")


class SaveIn(BaseModel):
    draft: dict
    expected_version: int = Field(default=0, ge=0)


class PublishIn(BaseModel):
    version: int = Field(ge=1)


class ReserveIn(BaseModel):
    operation_ref: str | None = Field(default=None, min_length=2, max_length=80)
    verification_note: str | None = Field(default=None, max_length=500)


class NoteIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


def _call(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except campaigns.Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(404, str(exc.args[0] if exc.args else exc)) from exc
    except ValidationError as exc:
        raise HTTPException(422, "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())) from exc
    except ValueError as exc:  # incluye BenefitRejected
        raise HTTPException(422, str(exc)) from exc


def _draft(raw: dict) -> campaigns.CampaignDraft:
    return _call(campaigns.CampaignDraft.model_validate, raw)


@router.get("/campaigns")
def index(user=Depends(auth.require("config:read"))):
    return {"campaigns": campaigns.inventory()}


@router.get("/campaigns/routes")
def routes(user=Depends(auth.require("config:read"))):
    """Rutas con tipo de cambio publicado por Brasper; el panel no asume combinaciones."""
    return {"routes": campaigns.available_routes()}


@router.get("/campaigns/{campaign_id}/history")
def history(campaign_id: str, user=Depends(auth.require("config:read"))):
    return {"versions": _call(campaigns.history, campaign_id)}


@router.post("/campaigns")
def create(body: SaveIn, user=Depends(auth.require("tenants:write"))):
    result = _call(campaigns.save, _draft(body.draft), user["email"], None, body.expected_version)
    db.add_audit_event(user["email"], "campaign.draft", f"campaign:{result['id']}", {"version": result["version"]})
    return result


@router.put("/campaigns/{campaign_id}")
def save(campaign_id: str, body: SaveIn, user=Depends(auth.require("tenants:write"))):
    result = _call(campaigns.save, _draft(body.draft), user["email"], campaign_id, body.expected_version)
    db.add_audit_event(user["email"], "campaign.draft", f"campaign:{campaign_id}", {"version": result["version"]})
    return result


@router.post("/campaigns/{campaign_id}/publish")
def publish(campaign_id: str, body: PublishIn, user=Depends(auth.require("tenants:write"))):
    result = _call(campaigns.publish, campaign_id, body.version, user["email"])
    db.add_audit_event(user["email"], "campaign.publish", f"campaign:{campaign_id}", body.model_dump())
    return result


@router.post("/campaigns/{campaign_id}/disable")
def disable(campaign_id: str, user=Depends(auth.require("tenants:write"))):
    result = _call(campaigns.disable, campaign_id)
    db.add_audit_event(user["email"], "campaign.disable", f"campaign:{campaign_id}", {})
    return result


@router.get("/campaigns/{campaign_id}/benefits")
def campaign_benefits(campaign_id: str, user=Depends(auth.require("config:read"))):
    return {"benefits": campaigns.benefits(campaign_id=campaign_id)}


def _conversation_for(user: dict, conversation_id: str) -> dict:
    from api.routes import _assert_conversation_access
    conv = db.get_conversation(conversation_id)
    if not conv:
        raise HTTPException(404, "Conversación no encontrada")
    _assert_conversation_access(user, conv)
    return conv


@router.get("/conversations/{conversation_id}/campaign-benefits")
def conversation_benefits(conversation_id: str, user=Depends(auth.require("conversations:read"))):
    _conversation_for(user, conversation_id)
    return {"benefits": campaigns.benefits(conversation_id=conversation_id),
            "eligibility": campaigns.eligibility(db.get_lead_data(conversation_id))}


@router.post("/cases/{case_id}/benefit")
def reserve(case_id: str, body: ReserveIn, user=Depends(auth.require("conversations:write"))):
    """Reserva la promoción aceptada en el expediente (ruta, monto y versión de la aceptación)."""
    case = _case_for(user, case_id)
    from core import lead_onboarding
    conv = db.get_conversation(case["conversation_id"]) or {}
    # Historial oficial justo antes de reservar (cuando Brasper lo expone).
    lead_onboarding.refresh_history(case["conversation_id"], conv.get("channel", "webchat"), conv.get("user_ref", ""))
    result = _call(campaigns.reserve, case_id, user["email"], operation_ref=body.operation_ref,
                   verification_note=body.verification_note)
    db.add_audit_event(user["email"], "campaign.benefit_reserved", f"case:{case_id}",
                       {"benefit_id": result["id"], "eligibility_source": result["eligibility_source"]})
    return result


def _benefit_conversation(user: dict, benefit_id: str) -> None:
    row = campaigns.benefit(benefit_id)
    if not row:
        raise HTTPException(404, "Beneficio no encontrado")
    if row.get("conversation_id"):
        _conversation_for(user, row["conversation_id"])


@router.post("/campaign-benefits/{benefit_id}/consume")
def consume(benefit_id: str, body: NoteIn, user=Depends(auth.require("conversations:write"))):
    _benefit_conversation(user, benefit_id)
    result = _call(campaigns.consume, benefit_id, user["email"], body.note)
    db.add_audit_event(user["email"], "campaign.benefit_consumed", f"campaign_benefit:{benefit_id}", {})
    return result


@router.post("/campaign-benefits/{benefit_id}/release")
def release(benefit_id: str, body: NoteIn, user=Depends(auth.require("conversations:write"))):
    _benefit_conversation(user, benefit_id)
    result = _call(campaigns.release, benefit_id, user["email"], body.note)
    db.add_audit_event(user["email"], "campaign.benefit_released", f"campaign_benefit:{benefit_id}", {})
    return result


class RegisterIn(BaseModel):
    operation_ref: str = Field(min_length=2, max_length=80)


class ExpireIn(BaseModel):
    note: str = Field(min_length=3, max_length=500)


@router.post("/campaign-benefits/{benefit_id}/expire")
def expire(benefit_id: str, body: ExpireIn, user=Depends(auth.require("conversations:write"))):
    _benefit_conversation(user, benefit_id)
    result = _call(campaigns.expire, benefit_id, user["email"], body.note)
    db.add_audit_event(user["email"], "campaign.benefit_expired", f"campaign_benefit:{benefit_id}", {})
    return result


@router.get("/campaign-benefits/{benefit_id}/transitions")
def benefit_transitions(benefit_id: str, user=Depends(auth.require("conversations:read"))):
    _benefit_conversation(user, benefit_id)
    return {"transitions": campaigns.transitions(benefit_id)}


@router.get("/conversations/{conversation_id}/case")
def conversation_case(conversation_id: str, user=Depends(auth.require("conversations:read"))):
    _conversation_for(user, conversation_id)
    return {"case": cases.view(cases.active_case(conversation_id))}


def _case_for(user: dict, case_id: str) -> dict:
    case = cases.get(case_id)
    if not case:
        raise HTTPException(404, "Expediente no encontrado")
    _conversation_for(user, case["conversation_id"])
    return case


@router.post("/cases/{case_id}/register")
def register_case(case_id: str, body: RegisterIn, user=Depends(auth.require("conversations:write"))):
    _case_for(user, case_id)
    result = _call(cases.register, case_id, body.operation_ref, user["email"])
    db.add_audit_event(user["email"], "case.registered", f"case:{case_id}", {"operation_ref": body.operation_ref})
    return {"case": cases.view(result)}


@router.post("/cases/{case_id}/close")
def close_case(case_id: str, cancelled: bool = False, user=Depends(auth.require("conversations:write"))):
    _case_for(user, case_id)
    result = _call(cases.close, case_id, user["email"], cancelled)
    db.add_audit_event(user["email"], "case.cancelled" if cancelled else "case.closed", f"case:{case_id}", {})
    return {"case": cases.view(result)}


import uuid
from datetime import datetime, timezone


class WebchatFlowUseCase:
    DOCUMENT_OPTIONS = [
        {"label": "DNI", "value": "dni"},
        {"label": "Pasaporte", "value": "passport"},
        {"label": "Carnet de extranjería", "value": "ce"},
        {"label": "RUC", "value": "ruc"},
    ]
    PROFILE_OPTIONS = [
        {"label": "Persona", "value": "person"},
        {"label": "Empresa", "value": "company"},
    ]

    def __init__(self, cache_adapter, persistence_adapter, client_directory, chat_use_case):
        self.cache_adapter = cache_adapter
        self.persistence_adapter = persistence_adapter
        self.client_directory = client_directory
        self.chat_use_case = chat_use_case

    def _session_key(self, session_id: str) -> str:
        return f"webchat:session:{session_id}"

    def _history_key(self, session_id: str) -> str:
        return f"webchat:history:{session_id}"

    def _lead_key(self, session_id: str) -> str:
        return f"webchat:lead:{session_id}"

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _message(self, role: str, text: str) -> dict:
        return {"id": str(uuid.uuid4()), "role": role, "text": text}

    def _default_session(self, session_id: str) -> dict:
        return {
            "id": session_id,
            "channel": "webchat",
            "status": "active",
            "current_step": "choose_profile_type",
            "profile_type": None,
            "document_type": None,
            "document_number": None,
            "customer_id": None,
            "lead_id": str(uuid.uuid4()),
            "customer_status": "pending",
            "lead_status": "capturing",
            "session_context": {"chat_ready": False},
            "last_user_message_at": None,
            "created_at": self._now(),
            "updated_at": self._now(),
        }

    def _save_session(self, session: dict):
        self.cache_adapter.save(self._session_key(session["id"]), session, ttl=None)
        self.persistence_adapter.upsert_session(session)

    def _save_history(self, session_id: str, messages: list[dict]):
        self.cache_adapter.save(self._history_key(session_id), messages[-40:], ttl=None)

    def _append_history(self, session_id: str, *messages: dict):
        history = self.cache_adapter.get(self._history_key(session_id)) or []
        history.extend(messages)
        self._save_history(session_id, history)
        return history

    def _get_history(self, session_id: str):
        return self.cache_adapter.get(self._history_key(session_id)) or []

    def _save_lead(self, session: dict, **lead_updates):
        lead = self.cache_adapter.get(self._lead_key(session["id"])) or {
            "id": session["lead_id"],
            "session_id": session["id"],
            "source_channel": "webchat",
            "first_seen_at": session["created_at"],
        }
        lead.update({k: v for k, v in lead_updates.items() if v is not None})
        self.cache_adapter.save(self._lead_key(session["id"]), lead, ttl=None)
        self.persistence_adapter.upsert_lead(lead)
        return lead

    def _build_response(self, session: dict, messages: list[dict], *, input_mode: str, options=None, customer_profile=None):
        lead = self.cache_adapter.get(self._lead_key(session["id"])) or {}
        return {
            "session_id": session["id"],
            "messages": messages,
            "step": session["current_step"],
            "input_mode": input_mode,
            "options": options or [],
            "customer_status": session.get("customer_status", "pending"),
            "customer_profile": customer_profile,
            "lead_status": session.get("lead_status", "capturing"),
            "lead_profile": lead,
        }

    def start_session(self, session_id: str | None = None):
        session_id = session_id or str(uuid.uuid4())
        session = self.cache_adapter.get(self._session_key(session_id)) or self.persistence_adapter.get_session(session_id)
        if session:
            self.cache_adapter.save(self._session_key(session_id), session, ttl=None)
            history = self._get_history(session_id)
            if history:
                step = session["current_step"]
                return self._build_response(
                    session,
                    history,
                    input_mode="text" if step in {"enter_document_number", "confirm_or_complete_profile", "free_chat"} else "options",
                    options=self.PROFILE_OPTIONS if step == "choose_profile_type" else self.DOCUMENT_OPTIONS if step == "choose_document_type" else [],
                    customer_profile=session.get("session_context", {}).get("customer_profile"),
                )

        session = self._default_session(session_id)
        assistant_messages = [
            self._message("assistant", "Hola, ¡Bienvenido a TKambio!"),
            self._message("assistant", "¿Quieres iniciar el chat como Persona o Empresa?"),
        ]
        self._save_session(session)
        self._save_history(session_id, assistant_messages)
        self._save_lead(session, lead_stage="new", customer_found=False)
        return self._build_response(session, assistant_messages, input_mode="options", options=self.PROFILE_OPTIONS)

    def _validate_document(self, document_type: str, document_number: str):
        number = self.client_directory.normalize_document_number(document_type, document_number)
        if document_type == "dni":
            return number.isdigit() and len(number) == 8
        if document_type == "ruc":
            return number.isdigit() and len(number) == 11
        if document_type in {"passport", "ce"}:
            compact = number.replace("-", "").replace(" ", "")
            return compact.isalnum() and 6 <= len(compact) <= 20
        return False

    def handle_message(self, session_id: str, message: str):
        session = self.cache_adapter.get(self._session_key(session_id)) or self.persistence_adapter.get_session(session_id)
        if not session:
            return self.start_session(session_id)

        text = str(message or "").strip()
        if not text:
            history = self._get_history(session_id)
            return self._build_response(session, history, input_mode="text")

        user_message = self._message("user", text)
        session["last_user_message_at"] = self._now()
        step = session["current_step"]

        if step == "choose_profile_type":
            normalized = text.lower()
            if normalized not in {"person", "company"}:
                assistant = self._message("assistant", "Seleccione una opción válida para continuar.")
                history = self._append_history(session_id, user_message, assistant)
                return self._build_response(session, history, input_mode="options", options=self.PROFILE_OPTIONS)
            session["profile_type"] = normalized
            session["current_step"] = "choose_document_type"
            self._save_session(session)
            self._save_lead(session, profile_type=normalized, lead_stage="identifying")
            assistant = self._message("assistant", "Para una mejor atención indique su tipo de documento:")
            history = self._append_history(session_id, user_message, assistant)
            return self._build_response(session, history, input_mode="options", options=self.DOCUMENT_OPTIONS)

        if step == "choose_document_type":
            normalized = self.client_directory.normalize_document_type(text)
            allowed = {item["value"] for item in self.DOCUMENT_OPTIONS}
            if normalized not in allowed:
                assistant = self._message("assistant", "Seleccione un tipo de documento válido.")
                history = self._append_history(session_id, user_message, assistant)
                return self._build_response(session, history, input_mode="options", options=self.DOCUMENT_OPTIONS)
            session["document_type"] = normalized
            session["current_step"] = "enter_document_number"
            self._save_session(session)
            self._save_lead(session, document_type=normalized)
            assistant = self._message("assistant", "Por favor ingrese su número de documento.")
            history = self._append_history(session_id, user_message, assistant)
            return self._build_response(session, history, input_mode="text")

        if step == "enter_document_number":
            document_type = session["document_type"]
            normalized_number = self.client_directory.normalize_document_number(document_type, text)
            if not self._validate_document(document_type, normalized_number):
                assistant = self._message("assistant", "El número de documento no tiene un formato válido para ese tipo.")
                history = self._append_history(session_id, user_message, assistant)
                return self._build_response(session, history, input_mode="text")

            session["document_number"] = normalized_number
            validating = self._message("assistant", "Por favor espere un momento que estamos validando sus datos.")
            history = self._append_history(session_id, user_message, validating)

            customer = self.client_directory.find_by_document(document_type, normalized_number)
            if customer:
                full_name = " ".join(filter(None, [customer.get("names"), customer.get("lastnames")])).strip()
                session["customer_id"] = customer.get("id")
                session["customer_status"] = "identified"
                session["lead_status"] = "qualified_existing_customer"
                session["current_step"] = "free_chat"
                session["session_context"] = {
                    **(session.get("session_context") or {}),
                    "chat_ready": True,
                    "customer_profile": customer,
                    "chat_identity": f"customer:{customer.get('id')}",
                }
                self._save_session(session)
                self._save_lead(
                    session,
                    profile_type=session.get("profile_type"),
                    document_type=document_type,
                    document_number=normalized_number,
                    names=customer.get("names"),
                    lastnames=customer.get("lastnames"),
                    email=customer.get("email"),
                    phone=customer.get("phone"),
                    customer_found=True,
                    customer_id=customer.get("id"),
                    lead_stage="existing_customer",
                )
                ready = self._message("assistant", f"Encontré sus datos, {full_name or 'cliente'}. Ya puede continuar con su consulta.")
                history.append(ready)
                self._save_history(session_id, history)
                return self._build_response(session, history, input_mode="text", customer_profile=customer)

            session["customer_status"] = "not_found"
            session["lead_status"] = "capturing"
            session["current_step"] = "confirm_or_complete_profile"
            self._save_session(session)
            self._save_lead(
                session,
                profile_type=session.get("profile_type"),
                document_type=document_type,
                document_number=normalized_number,
                customer_found=False,
                lead_stage="awaiting_name",
            )
            assistant = self._message("assistant", "No encontré sus datos. Me puede brindar su nombre y apellidos.")
            history.append(assistant)
            self._save_history(session_id, history)
            return self._build_response(session, history, input_mode="text")

        if step == "confirm_or_complete_profile":
            parts = [part for part in text.split() if part]
            names = parts[0] if parts else text
            lastnames = " ".join(parts[1:]) if len(parts) > 1 else ""
            session["current_step"] = "free_chat"
            session["session_context"] = {
                **(session.get("session_context") or {}),
                "chat_ready": True,
                "captured_profile": {"names": names, "lastnames": lastnames},
                "chat_identity": f"web:{session['id']}",
            }
            session["lead_status"] = "captured_new_lead"
            self._save_session(session)
            self._save_lead(session, names=names, lastnames=lastnames, lead_stage="captured_profile")
            assistant = self._message("assistant", f"Gracias {names}. Ya puede continuar con su consulta.")
            history = self._append_history(session_id, user_message, assistant)
            return self._build_response(session, history, input_mode="text")

        chat_identity = session.get("session_context", {}).get("chat_identity") or f"web:{session['id']}"
        answer = self.chat_use_case.execute(chat_identity, text)
        assistant = self._message("assistant", answer)
        history = self._append_history(session_id, user_message, assistant)
        self._save_session(session)
        self._save_lead(
            session,
            profile_type=session.get("profile_type"),
            document_type=session.get("document_type"),
            document_number=session.get("document_number"),
            customer_found=session.get("customer_status") == "identified",
            customer_id=session.get("customer_id"),
            lead_stage="chatting",
            conversation_summary=answer[:500],
        )
        return self._build_response(session, history, input_mode="text", customer_profile=session.get("session_context", {}).get("customer_profile"))

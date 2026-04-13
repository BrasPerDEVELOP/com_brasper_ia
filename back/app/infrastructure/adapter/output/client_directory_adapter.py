import json
import os
from pathlib import Path


class ClientDirectoryAdapter:
    DOCUMENT_ALIASES = {
        "dni": "dni",
        "passport": "passport",
        "pasaporte": "passport",
        "ce": "ce",
        "carnet de extranjeria": "ce",
        "carnet de extr.": "ce",
        "ruc": "ruc",
    }

    def __init__(self, persistence_adapter):
        self.persistence_adapter = persistence_adapter
        self._seed_if_available()

    def _seed_if_available(self):
        seed_path = os.getenv("CLIENT_DIRECTORY_JSON")
        if not seed_path:
            return
        file_path = Path(seed_path)
        if not file_path.exists():
            return
        try:
            payload = json.loads(file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(payload, list):
            self.persistence_adapter.seed_clients(payload)

    def normalize_document_type(self, document_type: str | None) -> str | None:
        if not document_type:
            return None
        normalized = str(document_type).strip().lower()
        return self.DOCUMENT_ALIASES.get(normalized, normalized)

    def normalize_document_number(self, document_type: str, document_number: str | None) -> str:
        raw = str(document_number or "").strip()
        normalized_type = self.normalize_document_type(document_type) or document_type
        return raw.upper() if normalized_type in {"passport", "ce"} else raw

    def find_by_document(self, document_type: str, document_number: str) -> dict | None:
        normalized_type = self.normalize_document_type(document_type)
        if not normalized_type:
            return None
        normalized_number = self.normalize_document_number(normalized_type, document_number)
        return self.persistence_adapter.find_client(normalized_type, normalized_number)

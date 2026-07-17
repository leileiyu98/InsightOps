"""Shared deterministic serialization and content-digest helpers."""

import hashlib
import json
import unicodedata
from pathlib import Path
from typing import Any


def canonical_json_bytes(payload: Any) -> bytes:
    """Serialize JSON-compatible data with the project's canonical encoding."""
    return json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_json_digest(payload: Any) -> str:
    """Return SHA-256 over the canonical JSON encoding."""
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def normalize_business_definition_content(raw: bytes) -> bytes:
    """Normalize Business Definitions content using sha256-nfc-lf-v1."""
    text = raw.decode("utf-8-sig", errors="strict")
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.rstrip("\n") + "\n"
    return text.encode("utf-8")


def compute_business_definition_digest(document_path: Path) -> str:
    """Hash normalized Business Definitions document content."""
    normalized = normalize_business_definition_content(document_path.read_bytes())
    return hashlib.sha256(normalized).hexdigest()

"""Tests for shared canonical JSON and Business Definitions content digests."""

from pathlib import Path

from insightops.canonical import (
    canonical_json_bytes,
    compute_business_definition_digest,
    normalize_business_definition_content,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_canonical_json_preserves_the_existing_project_encoding() -> None:
    assert canonical_json_bytes({"z": 1, "a": "增长"}) == '{"a":"增长","z":1}'.encode()


def test_business_definition_normalization_is_nfc_lf_with_one_terminal_lf() -> None:
    decomposed_crlf = b"Cafe\xcc\x81\r\n\r\n"
    normalized_lf = "Café\n".encode()

    assert normalize_business_definition_content(decomposed_crlf) == normalized_lf


def test_business_definition_document_digest_is_frozen() -> None:
    assert (
        compute_business_definition_digest(PROJECT_ROOT / "docs" / "business-definitions-v1.md")
        == "eb759951171f377c5c33a199d06d98dd4ebf0529b66d4e950ea8f622a778500d"
    )

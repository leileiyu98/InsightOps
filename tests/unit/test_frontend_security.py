"""Static security regression checks for the React source boundary."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ROOT = PROJECT_ROOT / "frontend"
SOURCE_SUFFIXES = {".html", ".js", ".ts", ".tsx"}


def _frontend_sources() -> dict[Path, str]:
    return {
        path: path.read_text(encoding="utf-8")
        for path in FRONTEND_ROOT.rglob("*")
        if path.is_file()
        and path.suffix in SOURCE_SUFFIXES
        and "node_modules" not in path.parts
        and "dist" not in path.parts
    }


def test_frontend_source_avoids_unsafe_execution_and_credentials() -> None:
    sources = _frontend_sources()
    production_sources = {
        path: content for path, content in sources.items() if "test" not in path.parts
    }
    combined = "\n".join(production_sources.values())

    assert "dangerouslySetInnerHTML" not in combined
    assert "eval(" not in combined
    assert "new Function" not in combined
    assert "VITE_OPENAI_API_KEY" not in combined
    assert "localStorage" not in combined
    assert "sessionStorage" not in combined
    assert "http://localhost" not in combined
    assert "https://" not in combined


def test_query_request_has_only_question_and_optional_case_id() -> None:
    api_source = (FRONTEND_ROOT / "src" / "api" / "query.ts").read_text(encoding="utf-8")
    request_type = (FRONTEND_ROOT / "src" / "types" / "query.ts").read_text(encoding="utf-8")

    assert "body: JSON.stringify(payload)" in api_source
    assert "question: string" in request_type
    assert "case_id?: string" in request_type
    for forbidden_field in ("provider:", "model:", "api_key:", "sql:"):
        request_block = request_type.split("export interface QueryRequest", maxsplit=1)[1].split(
            "}", maxsplit=1
        )[0]
        assert forbidden_field not in request_block


def test_api_content_is_rendered_as_react_text() -> None:
    components = (
        FRONTEND_ROOT / "src" / "components" / "SqlPanel.tsx",
        FRONTEND_ROOT / "src" / "components" / "BusinessSummary.tsx",
        FRONTEND_ROOT / "src" / "components" / "ClarificationPanel.tsx",
    )

    combined = "\n".join(path.read_text(encoding="utf-8") for path in components)
    assert "{sql}" in combined
    assert "{summary}" in combined
    assert "{question}" in combined
    assert "innerHTML" not in combined

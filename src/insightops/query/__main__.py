"""Command-line demo for the M1.3 Text2SQL flow."""

import argparse
import json
from typing import Never

from insightops.core.config import load_settings
from insightops.query.contracts import QueryRequest
from insightops.query.runtime import build_query_service
from insightops.query.service import QueryService, QueryServiceError


def main() -> None:
    parser = argparse.ArgumentParser(description="Run one InsightOps Text2SQL demo query.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--case-id")
    parser.add_argument("--provider", choices=("fake", "openai"), default=None)
    args = parser.parse_args()

    settings = load_settings()
    if args.provider is not None:
        settings = settings.model_copy(update={"query_provider": args.provider})
    service: QueryService | None = None
    try:
        service = build_query_service(settings)
        response = service.query(QueryRequest(question=args.question, case_id=args.case_id))
    except QueryServiceError as error:
        _exit_with_error(error)
    finally:
        if service is not None:
            service.close()
    print(json.dumps(response.model_dump(mode="json"), ensure_ascii=False, indent=2))


def _exit_with_error(error: QueryServiceError) -> Never:
    payload = {"code": error.code, "message": error.message}
    raise SystemExit(json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()

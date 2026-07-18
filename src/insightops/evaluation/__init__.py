"""Public contracts and loaders for deterministic SQL evaluation."""

from insightops.evaluation.contracts import (
    CandidateSubmission,
    CaseEvaluationResult,
    EvaluationReport,
    EvaluationSuiteManifest,
    ExecuteSqlResponse,
    RequestClarificationResponse,
    SqlAnalysisResult,
)
from insightops.evaluation.runner import EvaluationRunner
from insightops.evaluation.sql_analysis import analyze_candidate_sql
from insightops.evaluation.suite import load_evaluation_suite, validate_candidate_submission

__all__ = [
    "CandidateSubmission",
    "CaseEvaluationResult",
    "EvaluationReport",
    "EvaluationSuiteManifest",
    "ExecuteSqlResponse",
    "RequestClarificationResponse",
    "SqlAnalysisResult",
    "EvaluationRunner",
    "analyze_candidate_sql",
    "load_evaluation_suite",
    "validate_candidate_submission",
]

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.safe_sql import summarize_sql
from app.services.tsql_analyzer import (
    analyze_control_flow,
    analyze_data_changes,
    analyze_error_handling,
    analyze_migration_impacts,
    analyze_references,
    analyze_transactions,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Reason:
    id: str
    impact: str
    weight: int
    message: str


@dataclass(frozen=True)
class Recommendation:
    id: str
    message: str


def evaluate_reusability(sql: str, dialect: str = "tsql", max_reason_items: int = 20) -> dict:
    """Evaluate reusability/utility candidacy for a single T-SQL SP/FN definition.

    Scoring model (deterministic): start at 100, subtract penalties, apply bonus, clamp 0..100.
    """
    summary = summarize_sql(sql)
    logger.info(
        "evaluate_reusability: sql_len=%s sql_hash=%s",
        summary["len"],
        summary["sha256_8"],
    )

    references = analyze_references(sql, dialect)
    transactions = analyze_transactions(sql)
    impacts = analyze_migration_impacts(sql)
    control_flow = analyze_control_flow(sql, dialect)
    data_changes = analyze_data_changes(sql, dialect)
    error_handling = analyze_error_handling(sql)

    tables = references["references"]["tables"]
    functions = references["references"]["functions"]
    table_count = len(tables)
    function_call_count = len(functions)

    cyclomatic_complexity = control_flow["control_flow"]["summary"]["cyclomatic_complexity"]
    has_writes = data_changes["data_changes"]["has_writes"]
    read_only = not has_writes
    uses_transaction = transactions["uses_transaction"]

    impact_ids = {item["id"] for item in impacts["items"]}
    has_dynamic_sql = "IMP_DYN_SQL" in impact_ids
    has_cursor = "IMP_CURSOR" in impact_ids
    uses_temp_objects = bool({"IMP_TEMP_TABLE", "IMP_TABLE_VARIABLE"} & impact_ids)
    external_system_impact = bool({"IMP_LINKED_SERVER", "IMP_SYSTEM_PROC"} & impact_ids)

    error_signaling = _error_signaling(error_handling)
    has_try_catch = error_handling["has_try_catch"]

    score = 100
    reasons: list[Reason] = []
    recommendations: list[Recommendation] = []

    def add_reason(reason: Reason) -> None:
        reasons.append(reason)

    def add_recommendation(rec: Recommendation) -> None:
        recommendations.append(rec)

    if has_writes:
        score -= 25
        add_reason(
            Reason(
                id="RSN_WRITES",
                impact="-",
                weight=25,
                message="Data writes reduce portability for reusable utilities.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REDUCE_WRITES",
                message="Minimize writes or isolate mutating logic for safer reuse.",
            )
        )
    else:
        add_reason(
            Reason(
                id="RSN_READ_ONLY",
                impact="+",
                weight=15,
                message="Read-only logic is easier to reuse safely.",
            )
        )

    if uses_transaction:
        score -= 15
        add_reason(
            Reason(
                id="RSN_TXN",
                impact="-",
                weight=15,
                message="Explicit transactions complicate reuse and composition.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REVIEW_TXN",
                message="Revisit transaction boundaries to keep utilities composable.",
            )
        )

    if has_dynamic_sql:
        score -= 20
        add_reason(
            Reason(
                id="RSN_DYN_SQL",
                impact="-",
                weight=20,
                message="Dynamic SQL makes behavior harder to reuse and test.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_AVOID_DYNAMIC_SQL",
                message="Avoid dynamic SQL to improve portability and testability.",
            )
        )

    if has_cursor:
        score -= 20
        add_reason(
            Reason(
                id="RSN_CURSOR",
                impact="-",
                weight=20,
                message="Cursor usage often limits reuse due to imperative flow.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_AVOID_CURSOR",
                message="Prefer set-based logic instead of cursors for reuse.",
            )
        )

    if uses_temp_objects:
        score -= 10
        add_reason(
            Reason(
                id="RSN_TEMP_OBJECTS",
                impact="-",
                weight=10,
                message="Temporary objects reduce reuse across contexts.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REDUCE_TEMP_OBJECTS",
                message="Limit temp tables/variables to keep utilities lightweight.",
            )
        )

    if table_count > 5:
        table_penalty = min(20, (table_count - 5) * 2)
        score -= table_penalty
        add_reason(
            Reason(
                id="RSN_TABLE_COUNT",
                impact="-",
                weight=table_penalty,
                message="Large table footprints reduce reuse and portability.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REDUCE_TABLES",
                message="Reduce table dependencies or split into smaller utilities.",
            )
        )

    if cyclomatic_complexity > 5:
        complexity_penalty = min(20, (cyclomatic_complexity - 5) * 2)
        score -= complexity_penalty
        add_reason(
            Reason(
                id="RSN_COMPLEXITY",
                impact="-",
                weight=complexity_penalty,
                message="High control-flow complexity reduces reuse clarity.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REDUCE_COMPLEXITY",
                message="Simplify branching to improve utility reusability.",
            )
        )

    if external_system_impact:
        score -= 25
        add_reason(
            Reason(
                id="RSN_EXTERNAL_IMPACT",
                impact="-",
                weight=25,
                message="External/system dependencies reduce safe reuse.",
            )
        )
        add_recommendation(
            Recommendation(
                id="REC_REVIEW_EXTERNALS",
                message="Review linked/system dependencies for portability.",
            )
        )

    if (
        read_only
        and (not uses_transaction)
        and (not has_dynamic_sql)
        and cyclomatic_complexity <= 3
    ):
        score += 5
        add_reason(
            Reason(
                id="RSN_LOW_COMPLEXITY",
                impact="+",
                weight=5,
                message="Simple, read-only flow favors reuse.",
            )
        )

    score = max(0, min(100, score))

    grade = _grade(score)
    is_candidate = score >= 65
    candidate_type = _candidate_type(
        sql,
        has_writes=has_writes,
        read_only=read_only,
        table_count=table_count,
        cyclomatic_complexity=cyclomatic_complexity,
    )

    reasons_payload = _normalize_reasons(reasons, max_reason_items)
    recommendations_payload = _normalize_recommendations(recommendations)

    errors = _sorted_unique(
        references.get("errors", [])
        + control_flow.get("errors", [])
        + data_changes.get("errors", [])
    )

    return {
        "version": "2.2.0",
        "summary": {
            "score": score,
            "grade": grade,
            "is_candidate": is_candidate,
            "candidate_type": candidate_type,
        },
        "signals": {
            "read_only": read_only,
            "has_writes": has_writes,
            "uses_transaction": uses_transaction,
            "has_dynamic_sql": has_dynamic_sql,
            "has_cursor": has_cursor,
            "uses_temp_objects": uses_temp_objects,
            "cyclomatic_complexity": cyclomatic_complexity,
            "table_count": table_count,
            "function_call_count": function_call_count,
            "has_try_catch": has_try_catch,
            "error_signaling": error_signaling,
        },
        "reasons": reasons_payload,
        "recommendations": recommendations_payload,
        "errors": errors,
    }


def _error_signaling(error_handling: dict[str, object]) -> list[str]:
    signals: list[str] = []
    if error_handling.get("uses_throw"):
        signals.append("THROW")
    if error_handling.get("uses_raiserror"):
        signals.append("RAISERROR")
    if error_handling.get("uses_return"):
        signals.append("RETURN")
    return sorted(set(signals))


def _grade(score: int) -> str:
    if score >= 80:
        return "A"
    if score >= 65:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _candidate_type(
    sql: str,
    *,
    has_writes: bool,
    read_only: bool,
    table_count: int,
    cyclomatic_complexity: int,
) -> str | None:
    if has_writes:
        return "mutator"
    if read_only and table_count <= 3 and cyclomatic_complexity <= 3:
        return "lookup"
    if read_only and _has_guard_checks(sql):
        return "validation"
    return None


def _has_guard_checks(sql: str) -> bool:
    stripped = _strip_sql_comments(sql).lower()
    return bool(re.search(r"\bif\s+exists\b", stripped) or re.search(r"\bexists\s*\(", stripped))


def _strip_sql_comments(sql: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", no_block)


def _normalize_reasons(reasons: list[Reason], max_items: int) -> list[dict[str, object]]:
    by_id: dict[str, Reason] = {}
    for reason in reasons:
        if reason.id in by_id:
            continue
        by_id[reason.id] = reason

    sorted_reasons = sorted(
        by_id.values(),
        key=lambda item: (-abs(item.weight), item.id),
    )

    trimmed = sorted_reasons[: max(0, max_items)]
    return [
        {
            "id": reason.id,
            "impact": reason.impact,
            "weight": reason.weight,
            "message": reason.message,
        }
        for reason in trimmed
    ]


def _normalize_recommendations(
    recommendations: list[Recommendation],
) -> list[dict[str, str]]:
    by_id: dict[str, Recommendation] = {}
    for rec in recommendations:
        if rec.id in by_id:
            continue
        by_id[rec.id] = rec

    sorted_recs = sorted(by_id.values(), key=lambda item: item.id)
    return [{"id": rec.id, "message": rec.message} for rec in sorted_recs]


def _sorted_unique(items: list[str]) -> list[str]:
    return sorted({item for item in items if item})

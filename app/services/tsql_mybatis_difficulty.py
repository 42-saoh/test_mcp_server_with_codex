from __future__ import annotations

import logging
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
class FactorItem:
    id: str
    points: int
    message: str


@dataclass(frozen=True)
class RecommendationItem:
    id: str
    message: str


def evaluate_mybatis_difficulty(
    sql: str,
    obj_type: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    max_reason_items: int = 25,
) -> dict[str, object]:
    """Evaluate migration difficulty for MyBatis conversion.

    Scoring model (deterministic):
    - Base score 10.
    - Add points for signals, then clamp 0..100.
    """
    summary = summarize_sql(sql)
    logger.info(
        "evaluate_mybatis_difficulty: sql_len=%s sql_hash=%s obj_type=%s",
        summary["len"],
        summary["sha256_8"],
        obj_type.lower() if case_insensitive else obj_type,
    )

    references = analyze_references(sql, dialect)
    transactions = analyze_transactions(sql)
    impacts = analyze_migration_impacts(sql)
    control_flow = analyze_control_flow(sql, dialect)
    data_changes = analyze_data_changes(sql, dialect)
    error_handling = analyze_error_handling(sql)

    table_count = len(references["references"]["tables"])
    function_call_count = len(references["references"]["functions"])
    cyclomatic_complexity = control_flow["control_flow"]["summary"]["cyclomatic_complexity"]

    data_ops = data_changes["data_changes"]["operations"]
    write_ops = [op for op, payload in data_ops.items() if payload["count"] > 0]
    write_ops_sorted = sorted(write_ops)
    has_writes = data_changes["data_changes"]["has_writes"]

    impact_ids = {item["id"] for item in impacts["items"]}
    has_dynamic_sql = "IMP_DYN_SQL" in impact_ids
    has_cursor = "IMP_CURSOR" in impact_ids
    uses_temp_objects = bool({"IMP_TEMP_TABLE", "IMP_TABLE_VARIABLE"} & impact_ids)
    has_merge = "IMP_MERGE" in impact_ids or data_ops["merge"]["count"] > 0
    has_output_clause = (
        "IMP_OUTPUT_CLAUSE" in impact_ids or "OUTPUT" in data_changes["data_changes"]["signals"]
    )
    has_identity_retrieval = "IMP_IDENTITY" in impact_ids

    uses_transaction = transactions["uses_transaction"]
    has_try_catch = error_handling["has_try_catch"]
    uses_at_at_error = error_handling["uses_at_at_error"]

    error_signaling = _error_signaling(error_handling, case_insensitive)

    factors: list[FactorItem] = []

    def add_factor(item_id: str, points: int, message: str) -> None:
        factors.append(FactorItem(id=item_id, points=points, message=message))

    score = 10

    if has_dynamic_sql:
        score += 25
        add_factor(
            "FAC_DYN_SQL",
            25,
            "Dynamic SQL increases rewrite complexity and requires MyBatis dynamic tags or refactor.",
        )
    if has_cursor:
        score += 25
        add_factor(
            "FAC_CURSOR",
            25,
            "Cursor usage typically needs set-based rewrites when moving to MyBatis.",
        )
    if uses_temp_objects:
        score += 12
        add_factor(
            "FAC_TEMP_OBJECTS",
            12,
            "Temporary tables or table variables require alternative structures in Java/MyBatis.",
        )
    if has_merge:
        score += 10
        add_factor(
            "FAC_MERGE",
            10,
            "MERGE statements often need custom merge logic in MyBatis.",
        )
    if has_output_clause:
        score += 10
        add_factor(
            "FAC_OUTPUT",
            10,
            "OUTPUT clauses require explicit result handling in MyBatis.",
        )
    if has_identity_retrieval:
        score += 8
        add_factor(
            "FAC_IDENTITY",
            8,
            "Identity retrieval patterns add key handling complexity in MyBatis.",
        )
    if uses_transaction:
        score += 10
        add_factor(
            "FAC_TXN_IN_SQL",
            10,
            "Transaction statements inside SQL need careful boundary handling.",
        )
    if has_writes:
        score += 10
        add_factor(
            "FAC_WRITES",
            10,
            "Write operations increase migration complexity compared with read-only logic.",
        )

    if len(write_ops_sorted) > 1:
        multi_points = min(12, 3 * (len(write_ops_sorted) - 1))
        score += multi_points
        add_factor(
            "FAC_MULTI_WRITE_OPS",
            multi_points,
            "Multiple write operation types increase mapping complexity in MyBatis.",
        )

    if has_try_catch:
        score += 5
        add_factor(
            "FAC_TRY_CATCH",
            5,
            "TRY/CATCH blocks require aligned exception handling in Java.",
        )
    if uses_at_at_error:
        score += 8
        add_factor(
            "FAC_LEGACY_ERROR",
            8,
            "Legacy @@ERROR handling needs refactoring to Java exceptions.",
        )

    if cyclomatic_complexity > 5:
        complexity_points = min(20, 2 * (cyclomatic_complexity - 5))
        score += complexity_points
        add_factor(
            "FAC_COMPLEXITY",
            complexity_points,
            "Higher control flow complexity increases migration effort.",
        )

    if table_count > 6:
        table_points = min(14, 2 * (table_count - 6))
        score += table_points
        add_factor(
            "FAC_MANY_TABLES",
            table_points,
            "Large table fan-out increases query mapping complexity.",
        )

    if function_call_count > 10:
        score += 5
        add_factor(
            "FAC_MANY_FUNCS",
            5,
            "High function call volume can complicate migration logic.",
        )

    score = max(0, min(100, score))
    difficulty_level = _difficulty_level(score)
    estimated_work_units = min(20, max(0, round(score / 5)))

    is_rewrite_recommended = difficulty_level in {"low", "medium"} and not (
        has_cursor or has_dynamic_sql
    )

    confidence = _confidence_score(
        difficulty_level=difficulty_level,
        has_dynamic_sql=has_dynamic_sql,
        has_cursor=has_cursor,
        uses_temp_objects=uses_temp_objects,
        has_merge=has_merge,
        cyclomatic_complexity=cyclomatic_complexity,
    )

    factor_payload = _normalize_factors(factors)
    recommendation_payload = _recommendations_for_factors(
        factor_payload, difficulty_level, is_rewrite_recommended
    )

    factor_payload, recommendation_payload, truncated, truncation_error = _apply_max_items(
        factor_payload, recommendation_payload, max_reason_items
    )

    errors = _sorted_unique(
        references.get("errors", [])
        + control_flow.get("errors", [])
        + data_changes.get("errors", [])
    )
    if truncation_error:
        errors.append(truncation_error)

    return {
        "version": "3.3.0",
        "summary": {
            "difficulty_score": score,
            "difficulty_level": difficulty_level,
            "estimated_work_units": estimated_work_units,
            "is_rewrite_recommended": is_rewrite_recommended,
            "confidence": confidence,
            "truncated": truncated,
        },
        "signals": {
            "table_count": table_count,
            "function_call_count": function_call_count,
            "has_writes": has_writes,
            "write_ops": write_ops_sorted,
            "uses_transaction": uses_transaction,
            "has_dynamic_sql": has_dynamic_sql,
            "has_cursor": has_cursor,
            "uses_temp_objects": uses_temp_objects,
            "has_merge": has_merge,
            "has_output_clause": has_output_clause,
            "has_identity_retrieval": has_identity_retrieval,
            "has_try_catch": has_try_catch,
            "error_signaling": error_signaling,
            "cyclomatic_complexity": cyclomatic_complexity,
        },
        "factors": factor_payload,
        "recommendations": recommendation_payload,
        "errors": errors,
    }


def _difficulty_level(score: int) -> str:
    if score <= 24:
        return "low"
    if score <= 49:
        return "medium"
    if score <= 74:
        return "high"
    return "very_high"


def _confidence_score(
    difficulty_level: str,
    has_dynamic_sql: bool,
    has_cursor: bool,
    uses_temp_objects: bool,
    has_merge: bool,
    cyclomatic_complexity: int,
) -> float:
    if difficulty_level in {"low", "medium"} and not (
        has_dynamic_sql or has_cursor or uses_temp_objects or has_merge
    ):
        if cyclomatic_complexity <= 6:
            return 0.85
    if difficulty_level == "medium":
        return 0.75
    if difficulty_level == "high":
        return 0.65
    return 0.55


def _error_signaling(error_handling: dict[str, object], case_insensitive: bool) -> list[str]:
    signals: set[str] = set()
    if error_handling.get("has_try_catch"):
        signals.add("TRY/CATCH")
    if error_handling.get("uses_throw"):
        signals.add("THROW")
    if error_handling.get("uses_raiserror"):
        signals.add("RAISERROR")
    if error_handling.get("uses_at_at_error"):
        signals.add("@@ERROR")
    if error_handling.get("uses_return"):
        signals.add("RETURN_CODE")
    if error_handling.get("uses_output_error_params"):
        signals.add("OUTPUT_PARAM")
    if case_insensitive:
        return sorted({signal.upper() for signal in signals})
    return sorted(signals)


def _normalize_factors(factors: list[FactorItem]) -> list[dict[str, object]]:
    by_id: dict[str, FactorItem] = {}
    for factor in factors:
        if factor.id in by_id:
            continue
        by_id[factor.id] = factor
    sorted_factors = sorted(by_id.values(), key=lambda item: (-item.points, item.id))
    return [
        {"id": factor.id, "points": factor.points, "message": factor.message}
        for factor in sorted_factors
    ]


def _recommendations_for_factors(
    factors: list[dict[str, object]],
    difficulty_level: str,
    is_rewrite_recommended: bool,
) -> list[dict[str, str]]:
    factor_ids = {item["id"] for item in factors}
    recommendations: list[RecommendationItem] = []

    def add_recommendation(item_id: str, message: str) -> None:
        recommendations.append(RecommendationItem(id=item_id, message=message))

    if {"FAC_DYN_SQL", "FAC_CURSOR"} & factor_ids:
        add_recommendation(
            "REC_CALL_SP_FIRST",
            "Start with CallableStatement mapping, then refactor to MyBatis SQL.",
        )
        add_recommendation(
            "REC_REFRACTOR_DYNAMIC_SQL",
            "Refactor dynamic SQL into MyBatis <if> and <choose> constructs.",
        )
        add_recommendation(
            "REC_REPLACE_CURSOR",
            "Replace cursor logic with set-based queries or batch processing.",
        )
    if "FAC_TXN_IN_SQL" in factor_ids:
        add_recommendation(
            "REC_TX_BOUNDARY_REVIEW",
            "Review transaction boundaries for relocation to the service layer.",
        )
    if {"FAC_OUTPUT", "FAC_IDENTITY"} & factor_ids:
        add_recommendation(
            "REC_HANDLE_KEYS_AND_OUTPUT",
            "Plan for key retrieval and OUTPUT clause handling in MyBatis.",
        )
    if "FAC_COMPLEXITY" in factor_ids:
        add_recommendation(
            "REC_REDUCE_BRANCHING",
            "Reduce branching or split logic into smaller MyBatis mappings.",
        )
    if "FAC_TEMP_OBJECTS" in factor_ids:
        add_recommendation(
            "REC_REWRITE_TEMP_OBJECTS",
            "Rewrite temp table usage using collections or staging tables.",
        )
    if difficulty_level in {"low", "medium"} and is_rewrite_recommended:
        add_recommendation(
            "REC_DIRECT_REWRITE",
            "Proceed with direct SQL rewrite to MyBatis mapper statements.",
        )

    by_id: dict[str, RecommendationItem] = {}
    for rec in recommendations:
        if rec.id in by_id:
            continue
        by_id[rec.id] = rec
    return [
        {"id": rec.id, "message": rec.message}
        for rec in sorted(by_id.values(), key=lambda item: item.id)
    ]


def _apply_max_items(
    factors: list[dict[str, object]],
    recommendations: list[dict[str, str]],
    max_items: int,
) -> tuple[list[dict[str, object]], list[dict[str, str]], bool, str | None]:
    if max_items <= 0:
        return (
            [],
            [],
            True,
            "max_reason_items_exceeded: truncated factors and recommendations",
        )
    total = len(factors) + len(recommendations)
    if total <= max_items:
        return factors, recommendations, False, None
    if len(factors) >= max_items:
        return (
            factors[:max_items],
            [],
            True,
            "max_reason_items_exceeded: truncated factors and recommendations",
        )
    remaining = max_items - len(factors)
    return (
        factors,
        recommendations[:remaining],
        True,
        "max_reason_items_exceeded: truncated factors and recommendations",
    )


def _sorted_unique(items: list[str]) -> list[str]:
    return sorted({item for item in items if item})

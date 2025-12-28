from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass

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
class StrategyItem:
    id: str
    message: str


@dataclass(frozen=True)
class ReasonItem:
    id: str
    weight: int
    message: str


def recommend_mapping_strategy(
    sql: str,
    obj_type: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    target_style: str = "rewrite",
    max_items: int = 30,
) -> dict[str, object]:
    """Recommend a deterministic Java/MyBatis mapping strategy for a T-SQL SP/FN.

    Decision model (deterministic):
    - Default to rewrite unless risk signals demand call_sp_first.
    - target_style="call_sp_first" only allows rewrite for very safe inputs.
    """
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("recommend_mapping_strategy: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    references = analyze_references(sql, dialect)
    transactions = analyze_transactions(sql)
    impacts = analyze_migration_impacts(sql)
    control_flow = analyze_control_flow(sql, dialect)
    data_changes = analyze_data_changes(sql, dialect)
    error_handling = analyze_error_handling(sql)

    table_count = len(references["references"]["tables"])
    cyclomatic_complexity = control_flow["control_flow"]["summary"]["cyclomatic_complexity"]
    uses_transaction = transactions["uses_transaction"]
    has_try_catch = error_handling["has_try_catch"]

    data_ops = data_changes["data_changes"]["operations"]
    has_writes = data_changes["data_changes"]["has_writes"]
    read_only = not has_writes
    write_kinds = _write_kinds(data_ops)

    impact_ids = {item["id"] for item in impacts["items"]}
    has_dynamic_sql = "IMP_DYN_SQL" in impact_ids
    has_cursor = "IMP_CURSOR" in impact_ids
    uses_temp_objects = bool({"IMP_TEMP_TABLE", "IMP_TABLE_VARIABLE"} & impact_ids)
    has_merge = "IMP_MERGE" in impact_ids or data_ops["merge"]["count"] > 0
    has_output_clause = (
        "IMP_OUTPUT_CLAUSE" in impact_ids or "OUTPUT" in data_changes["data_changes"]["signals"]
    )
    has_identity_retrieval = "IMP_IDENTITY" in impact_ids

    error_signaling = _error_signaling(error_handling)

    risk_signals = has_cursor or has_dynamic_sql or uses_temp_objects or has_merge

    approach = _choose_approach(
        target_style=target_style,
        risk_signals=risk_signals,
        uses_transaction=uses_transaction,
        has_writes=has_writes,
        cyclomatic_complexity=cyclomatic_complexity,
    )

    difficulty = _difficulty_level(
        has_writes=has_writes,
        uses_transaction=uses_transaction,
        cyclomatic_complexity=cyclomatic_complexity,
        has_dynamic_sql=has_dynamic_sql,
        has_cursor=has_cursor,
        uses_temp_objects=uses_temp_objects,
        has_merge=has_merge,
    )

    confidence = _confidence_score(
        approach=approach,
        read_only=read_only,
        has_writes=has_writes,
        uses_transaction=uses_transaction,
        has_dynamic_sql=has_dynamic_sql,
        has_cursor=has_cursor,
        uses_temp_objects=uses_temp_objects,
        has_merge=has_merge,
        cyclomatic_complexity=cyclomatic_complexity,
        write_kinds=write_kinds,
    )

    recommended_patterns, anti_patterns = _strategy_patterns(
        approach=approach,
        read_only=read_only,
        has_writes=has_writes,
        has_dynamic_sql=has_dynamic_sql,
    )
    reasons, recommendations = _reasons_and_recommendations(
        read_only=read_only,
        has_writes=has_writes,
        has_dynamic_sql=has_dynamic_sql,
        has_cursor=has_cursor,
        uses_temp_objects=uses_temp_objects,
        has_merge=has_merge,
        uses_transaction=uses_transaction,
        cyclomatic_complexity=cyclomatic_complexity,
        error_signaling=error_signaling,
        has_identity_retrieval=has_identity_retrieval,
        has_output_clause=has_output_clause,
        approach=approach,
    )

    errors = _sorted_unique(
        references.get("errors", [])
        + control_flow.get("errors", [])
        + data_changes.get("errors", [])
    )

    reasons_payload = _normalize_reasons(reasons)
    recommendations_payload = _normalize_recommendations(recommendations)
    reasons_payload, recommendations_payload, truncation_error = _apply_max_items(
        reasons_payload, recommendations_payload, max_items
    )
    if truncation_error:
        errors.append(truncation_error)

    mapper_method = _mapper_method(
        obj_type=obj_type,
        approach=approach,
        read_only=read_only,
        write_kinds=write_kinds,
    )
    xml_template = _xml_template(
        approach=approach,
        read_only=read_only,
        write_kinds=write_kinds,
        has_dynamic_sql=has_dynamic_sql,
    )

    return {
        "version": "3.1.0",
        "summary": {
            "approach": approach,
            "confidence": confidence,
            "difficulty": difficulty,
            "is_recommended": True,
        },
        "signals": {
            "read_only": read_only,
            "has_writes": has_writes,
            "writes_kind": write_kinds or ["select"],
            "uses_transaction": uses_transaction,
            "has_dynamic_sql": has_dynamic_sql,
            "has_cursor": has_cursor,
            "uses_temp_objects": uses_temp_objects,
            "has_merge": has_merge,
            "has_identity_retrieval": has_identity_retrieval,
            "has_output_clause": has_output_clause,
            "cyclomatic_complexity": cyclomatic_complexity,
            "table_count": table_count,
            "has_try_catch": has_try_catch,
            "error_signaling": error_signaling,
        },
        "strategy": {
            "migration_path": _migration_path(approach),
            "recommended_patterns": recommended_patterns,
            "anti_patterns": anti_patterns,
        },
        "mybatis": {
            "mapper_method": mapper_method,
            "xml_template": xml_template,
        },
        "java": {
            "service_pattern": {
                "transactional": uses_transaction and approach == "rewrite_to_mybatis_sql",
                "exception_mapping": "throw domain exception on error",
            },
            "dto_suggestions": [
                {
                    "id": "DTO_REQUEST",
                    "fields": ["..."],
                    "notes": "best-effort based on parameter markers; no SQL text",
                }
            ],
        },
        "reasons": reasons_payload,
        "recommendations": recommendations_payload,
        "errors": _sorted_unique(errors),
    }


def _choose_approach(
    *,
    target_style: str,
    risk_signals: bool,
    uses_transaction: bool,
    has_writes: bool,
    cyclomatic_complexity: int,
) -> str:
    risk_based = (
        risk_signals
        or cyclomatic_complexity >= 12
        or (uses_transaction and has_writes and cyclomatic_complexity >= 8)
    )
    approach = "call_sp_first" if risk_based else "rewrite_to_mybatis_sql"
    if target_style == "call_sp_first":
        if not risk_signals and cyclomatic_complexity <= 5:
            return "rewrite_to_mybatis_sql"
        return "call_sp_first"
    return approach


def _difficulty_level(
    *,
    has_writes: bool,
    uses_transaction: bool,
    cyclomatic_complexity: int,
    has_dynamic_sql: bool,
    has_cursor: bool,
    uses_temp_objects: bool,
    has_merge: bool,
) -> str:
    levels = ["low", "medium", "high", "very_high"]
    index = 0
    if has_writes:
        index += 1
    if uses_transaction:
        index += 1
    if cyclomatic_complexity > 8:
        index += 1
    risk_count = sum(
        1 for flag in [has_dynamic_sql, has_cursor, uses_temp_objects, has_merge] if flag
    )
    if risk_count:
        index += min(2, risk_count)
    return levels[min(index, len(levels) - 1)]


def _confidence_score(
    *,
    approach: str,
    read_only: bool,
    has_writes: bool,
    uses_transaction: bool,
    has_dynamic_sql: bool,
    has_cursor: bool,
    uses_temp_objects: bool,
    has_merge: bool,
    cyclomatic_complexity: int,
    write_kinds: list[str],
) -> float:
    risk_signals = has_dynamic_sql or has_cursor or uses_temp_objects or has_merge
    simple_write = (
        has_writes
        and len(write_kinds) == 1
        and not uses_transaction
        and not risk_signals
        and cyclomatic_complexity <= 6
    )
    if approach == "rewrite_to_mybatis_sql":
        if read_only and cyclomatic_complexity <= 5 and not risk_signals and not uses_transaction:
            base = 0.85
        elif simple_write:
            base = 0.75
        else:
            base = 0.65
    else:
        if risk_signals or cyclomatic_complexity >= 12:
            base = 0.85
        else:
            base = 0.65
    return max(0.5, min(0.9, base))


def _write_kinds(operations: dict[str, dict[str, object]]) -> list[str]:
    kinds = []
    for op in ["insert", "update", "delete", "merge", "truncate", "select_into"]:
        if operations[op]["count"] > 0:
            kinds.append(op)
    return kinds


def _strategy_patterns(
    *,
    approach: str,
    read_only: bool,
    has_writes: bool,
    has_dynamic_sql: bool,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    patterns: list[StrategyItem] = []
    anti_patterns: list[StrategyItem] = []

    def add_pattern(item_id: str, message: str) -> None:
        patterns.append(StrategyItem(id=item_id, message=message))

    def add_anti(item_id: str, message: str) -> None:
        anti_patterns.append(StrategyItem(id=item_id, message=message))

    if approach == "rewrite_to_mybatis_sql":
        if read_only:
            add_pattern(
                "PAT_SELECT_MAPPER",
                "Use <select> with resultType/resultMap for read queries.",
            )
        if has_writes:
            add_pattern(
                "PAT_DML_STATEMENTS",
                "Use <insert>/<update>/<delete> tags that match write operations.",
            )
        if has_dynamic_sql:
            add_pattern(
                "PAT_MYBATIS_DYNAMIC_TAGS",
                "Use MyBatis <if>/<choose>/<foreach> instead of string concatenation.",
            )
            add_anti(
                "ANTI_DYN_SQL_CONCAT",
                "Avoid string-concatenated dynamic SQL; use MyBatis dynamic tags.",
            )
    else:
        add_pattern(
            "PAT_CALLABLE_STATEMENT",
            "Use statementType=CALLABLE with IN/OUT param bindings.",
        )
        if has_dynamic_sql:
            add_anti(
                "ANTI_DYN_SQL_CONCAT",
                "Avoid string-concatenated dynamic SQL; use MyBatis dynamic tags.",
            )

    return (
        _normalize_strategy_items(patterns),
        _normalize_strategy_items(anti_patterns),
    )


def _reasons_and_recommendations(
    *,
    read_only: bool,
    has_writes: bool,
    has_dynamic_sql: bool,
    has_cursor: bool,
    uses_temp_objects: bool,
    has_merge: bool,
    uses_transaction: bool,
    cyclomatic_complexity: int,
    error_signaling: list[str],
    has_identity_retrieval: bool,
    has_output_clause: bool,
    approach: str,
) -> tuple[list[ReasonItem], list[StrategyItem]]:
    reasons: list[ReasonItem] = []
    recommendations: list[StrategyItem] = []

    if read_only and cyclomatic_complexity <= 5:
        reasons.append(
            ReasonItem(
                id="RSN_READ_ONLY_LOW_COMPLEXITY",
                weight=20,
                message="Read-only + low complexity favors direct SQL rewrite in MyBatis.",
            )
        )
        recommendations.append(
            StrategyItem(
                id="REC_RESULTMAP_FOR_JOINS",
                message=(
                    "Prefer resultMap when column aliases or joins increase mapping complexity."
                ),
            )
        )
    if has_writes:
        reasons.append(
            ReasonItem(
                id="RSN_HAS_WRITES",
                weight=15,
                message="Write operations increase migration care for MyBatis mappings.",
            )
        )
    if uses_transaction:
        recommendations.append(
            StrategyItem(
                id="REC_SERVICE_TXN_AWARE",
                message=(
                    "Prefer service-layer transaction demarcation in rewrite flows to avoid "
                    "nesting stored-proc transactions."
                ),
            )
        )
    if has_dynamic_sql:
        reasons.append(
            ReasonItem(
                id="RSN_DYNAMIC_SQL",
                weight=18,
                message="Dynamic SQL suggests an interim callable strategy or careful refactor.",
            )
        )
    if has_cursor:
        reasons.append(
            ReasonItem(
                id="RSN_CURSOR",
                weight=18,
                message="Cursor usage often requires an interim callable strategy.",
            )
        )
    if uses_temp_objects:
        reasons.append(
            ReasonItem(
                id="RSN_TEMP_OBJECTS",
                weight=12,
                message="Temporary objects add rewrite complexity.",
            )
        )
    if has_merge:
        reasons.append(
            ReasonItem(
                id="RSN_MERGE",
                weight=12,
                message="MERGE statements often need careful translation.",
            )
        )
    if cyclomatic_complexity >= 12:
        reasons.append(
            ReasonItem(
                id="RSN_HIGH_COMPLEXITY",
                weight=20,
                message="High control-flow complexity favors staged migration.",
            )
        )

    if "THROW" in error_signaling or "RAISERROR" in error_signaling:
        recommendations.append(
            StrategyItem(
                id="REC_MAP_TO_EXCEPTION",
                message="Map THROW/RAISERROR to custom domain exceptions with standardized codes.",
            )
        )
    if "@@ERROR" in error_signaling:
        recommendations.append(
            StrategyItem(
                id="REC_REMOVE_LEGACY_ERROR",
                message="Replace @@ERROR handling with TRY/CATCH + THROW in Java services.",
            )
        )
    if has_identity_retrieval:
        recommendations.append(
            StrategyItem(
                id="REC_USE_SELECTKEY_OR_RETURNING",
                message="Use MyBatis <selectKey> or follow-up selects for identity retrieval.",
            )
        )
    if has_output_clause:
        recommendations.append(
            StrategyItem(
                id="REC_OUTPUT_MAPPING",
                message="Map OUTPUT clause rows to DTOs via explicit resultMap definitions.",
            )
        )
    if approach == "call_sp_first":
        recommendations.append(
            StrategyItem(
                id="REC_REFRACTOR_LATER",
                message="Plan a later refactor into smaller MyBatis queries for target-state rewrite.",
            )
        )

    return reasons, recommendations


def _mapper_method(
    *,
    obj_type: str,
    approach: str,
    read_only: bool,
    write_kinds: list[str],
) -> dict[str, str]:
    name_prefix = "call" if approach == "call_sp_first" else ("select" if read_only else "execute")
    suffix = _camelize(obj_type)
    method_name = name_prefix + (suffix or "Object")

    kind = "call"
    if approach == "rewrite_to_mybatis_sql":
        if read_only:
            kind = "selectOne"
        elif len(write_kinds) == 1:
            kind = {
                "insert": "insert",
                "update": "update",
                "delete": "delete",
            }.get(write_kinds[0], "update")
        else:
            kind = "update"

    return {
        "name": method_name,
        "kind": kind,
        "parameter_style": "dto",
        "return_style": "dto",
    }


def _xml_template(
    *,
    approach: str,
    read_only: bool,
    write_kinds: list[str],
    has_dynamic_sql: bool,
) -> dict[str, object]:
    if approach == "call_sp_first":
        statement_tag = "select"
        skeleton = "CALLABLE template: {call proc_name(#{inParam,mode=IN},#{outParam,mode=OUT})}"
    elif read_only:
        statement_tag = "select"
        skeleton = "SELECT <columns> FROM <table> WHERE <conditions>"
    else:
        statement_tag = "update"
        if len(write_kinds) == 1:
            statement_tag = {
                "insert": "insert",
                "update": "update",
                "delete": "delete",
            }.get(write_kinds[0], "update")
        skeleton = "DML template: <statement> <table> <set/values> <where>"

    dynamic_tags = ["if", "choose", "foreach"] if has_dynamic_sql else []
    return {
        "statement_tag": statement_tag,
        "skeleton": skeleton,
        "dynamic_tags": dynamic_tags,
    }


def _migration_path(approach: str) -> list[str]:
    if approach == "call_sp_first":
        return ["intermediate_state", "target_state"]
    return ["target_state"]


def _normalize_strategy_items(items: list[StrategyItem]) -> list[dict[str, str]]:
    by_id: dict[str, StrategyItem] = {}
    for item in items:
        if item.id in by_id:
            continue
        by_id[item.id] = item
    return [
        {"id": item.id, "message": item.message}
        for item in sorted(by_id.values(), key=lambda item: item.id)
    ]


def _normalize_reasons(reasons: list[ReasonItem]) -> list[dict[str, object]]:
    by_id: dict[str, ReasonItem] = {}
    for reason in reasons:
        if reason.id in by_id:
            continue
        by_id[reason.id] = reason
    sorted_reasons = sorted(by_id.values(), key=lambda item: (-item.weight, item.id))
    return [
        {"id": reason.id, "weight": reason.weight, "message": reason.message}
        for reason in sorted_reasons
    ]


def _normalize_recommendations(
    recommendations: list[StrategyItem],
) -> list[dict[str, str]]:
    by_id: dict[str, StrategyItem] = {}
    for rec in recommendations:
        if rec.id in by_id:
            continue
        by_id[rec.id] = rec
    return [
        {"id": rec.id, "message": rec.message}
        for rec in sorted(by_id.values(), key=lambda item: item.id)
    ]


def _apply_max_items(
    reasons: list[dict[str, object]],
    recommendations: list[dict[str, str]],
    max_items: int,
) -> tuple[list[dict[str, object]], list[dict[str, str]], str | None]:
    if max_items <= 0:
        return [], [], "max_items_exceeded: truncated reasons and recommendations"
    total = len(reasons) + len(recommendations)
    if total <= max_items:
        return reasons, recommendations, None
    if len(reasons) >= max_items:
        return reasons[:max_items], [], "max_items_exceeded: truncated reasons and recommendations"
    remaining = max_items - len(reasons)
    return (
        reasons,
        recommendations[:remaining],
        "max_items_exceeded: truncated reasons and recommendations",
    )


def _error_signaling(error_handling: dict[str, object]) -> list[str]:
    signals: set[str] = set()
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
    return sorted(signals)


def _camelize(value: str) -> str:
    cleaned = value.split(".")[-1]
    if not cleaned:
        return ""
    cleaned = cleaned.replace("[", "").replace("]", "")
    for prefix in ("usp_", "ufn_", "fn_", "sp_", "trg_"):
        if cleaned.lower().startswith(prefix):
            cleaned = cleaned[len(prefix) :]
            break
    parts = [part for part in cleaned.replace("-", "_").split("_") if part]
    if not parts:
        return cleaned[:1].upper() + cleaned[1:]
    return "".join(part[:1].upper() + part[1:] for part in parts)


def _sorted_unique(items: list[str]) -> list[str]:
    return sorted({item for item in items if item})

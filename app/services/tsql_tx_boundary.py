# [파일 설명]
# - 목적: T-SQL 분석/추천 로직을 제공하는 서비스 모듈이다.
# - 제공 기능: 분석 결과 요약, 위험도 평가, 전략 추천 등의 함수를 포함한다.
# - 입력/출력: SQL 또는 옵션을 입력받아 구조화된 dict 결과를 반환한다.
# - 주의 사항: 원문 SQL은 요약/해시로만 다루며 직접 노출하지 않는다.
# - 연관 모듈: app.api.mcp 라우터에서 호출된다.
from __future__ import annotations

import logging
from dataclasses import dataclass

from app.services.safe_sql import summarize_sql
from app.services.tsql_analyzer import (
    analyze_control_flow,
    analyze_data_changes,
    analyze_error_handling,
    analyze_migration_impacts,
    analyze_transactions,
)

logger = logging.getLogger(__name__)


# [클래스 설명]
# - 역할: GuidanceItem 데이터 모델/구성 요소을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
@dataclass(frozen=True)
class GuidanceItem:
    id: str
    message: str


# [함수 설명]
# - 목적: recommend_transaction_boundary 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 주요 키는 summary, signals, suggestions, errors이다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def recommend_transaction_boundary(
    sql: str,
    obj_type: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    prefer_service_layer_tx: bool = True,
    max_items: int = 30,
) -> dict[str, object]:
    """Recommend deterministic transaction boundary guidance for a T-SQL SP/FN.

    Decision model (deterministic):
    - Read-only inputs avoid transactions (SUPPORTS, read_only=True).
    - Writes default to service-layer transactions (REQUIRED).
    - When SQL manages transactions, use hybrid guidance and avoid double-transactioning.
    - Confidence decreases with SQL-managed transactions, complexity, and rewrite risks.
    """
    summary = summarize_sql(sql)
    logger.info(
        "recommend_transaction_boundary: sql_len=%s sql_hash=%s",
        summary["len"],
        summary["sha256_8"],
    )

    transactions = analyze_transactions(sql)
    data_changes = analyze_data_changes(sql, dialect)
    error_handling = analyze_error_handling(sql)
    control_flow = analyze_control_flow(sql, dialect)
    impacts = analyze_migration_impacts(sql)

    data_ops = data_changes["data_changes"]["operations"]
    has_writes = data_changes["data_changes"]["has_writes"]
    write_ops = _write_ops(data_ops)

    uses_transaction_in_sql = bool(
        transactions["uses_transaction"]
        or transactions["begin_count"]
        or transactions["commit_count"]
        or transactions["rollback_count"]
    )

    has_try_catch = bool(transactions["has_try_catch"] or error_handling["has_try_catch"])
    isolation_level_in_sql = transactions["isolation_level"]
    xact_abort = transactions["xact_abort"]
    complexity = control_flow["control_flow"]["summary"]["cyclomatic_complexity"]

    impact_ids = {item["id"] for item in impacts["items"]}
    has_dynamic_sql = "IMP_DYN_SQL" in impact_ids
    has_cursor = "IMP_CURSOR" in impact_ids
    uses_temp_objects = bool({"IMP_TEMP_TABLE", "IMP_TABLE_VARIABLE"} & impact_ids)
    error_signaling = _error_signaling(error_handling)

    recommended_boundary = "service_layer" if prefer_service_layer_tx else "service_layer"
    transactional = True
    propagation = "REQUIRED"
    read_only = False
    confidence = 0.75 if has_writes else 0.85
    summary_isolation = None

    suggestions: list[GuidanceItem] = []
    anti_patterns: list[GuidanceItem] = []
    notes: list[str] = []

    if not has_writes:
        recommended_boundary = "none"
        transactional = False
        propagation = "SUPPORTS"
        read_only = True
        suggestions.extend(
            [
                GuidanceItem(
                    "SUG_NO_TX_READONLY",
                    "Do not open a transaction; keep method non-transactional.",
                ),
                GuidanceItem(
                    "SUG_OPTIONAL_READONLY_TX",
                    "Optionally use @Transactional(readOnly = true) if your platform benefits from it.",
                ),
            ]
        )
        notes.append("Read-only access can omit @Transactional by default.")
    elif not uses_transaction_in_sql:
        suggestions.append(
            GuidanceItem(
                "SUG_SERVICE_TX_REQUIRED",
                "@Transactional(REQUIRED) over the service method.",
            )
        )
        notes.append("Keep transaction scope minimal but spanning consistent write set.")

    if uses_transaction_in_sql and has_writes:
        recommended_boundary = "hybrid"
        rollback_in_catch = bool(has_try_catch and transactions["rollback_count"] > 0)
        propagation = "NOT_SUPPORTED" if rollback_in_catch else "REQUIRES_NEW"
        suggestions.extend(
            [
                GuidanceItem(
                    "SUG_AVOID_DOUBLE_TX",
                    "Avoid wrapping SP-managed transactions with Java transactions initially.",
                ),
                GuidanceItem(
                    "SUG_USE_NOT_SUPPORTED",
                    "Consider Propagation.NOT_SUPPORTED when calling SP that manages its own "
                    "transaction.",
                ),
            ]
        )
        anti_patterns.append(
            GuidanceItem(
                "ANTI_NESTED_TX",
                "Avoid nested/overlapping Java+TSQL transactions without clear ownership.",
            )
        )
        notes.append("Favor SP-owned transaction scope until refactor is complete.")

    if isolation_level_in_sql:
        summary_isolation = _normalize_isolation_level(isolation_level_in_sql)
        suggestions.append(
            GuidanceItem(
                "SUG_MATCH_ISOLATION",
                "Match SQL isolation level in Spring or keep it in DB at first.",
            )
        )

    if xact_abort == "ON":
        suggestions.append(
            GuidanceItem(
                "SUG_XACT_ABORT_ALIGN",
                "Ensure thrown exceptions trigger rollback to align with XACT_ABORT.",
            )
        )

    if error_handling.get("uses_throw") or error_handling.get("uses_raiserror"):
        suggestions.append(
            GuidanceItem(
                "SUG_ROLLBACK_ON_EXCEPTION",
                "Configure rollback on exceptions to mirror DB rollback behavior.",
            )
        )

    if complexity >= 12 or has_dynamic_sql or has_cursor or uses_temp_objects:
        anti_patterns.append(
            GuidanceItem(
                "ANTI_PARTIAL_TX",
                "Do not split writes into separate transactions if atomicity is required.",
            )
        )
        notes.append("Complex rewrites benefit from narrower, well-owned boundaries.")

    if error_signaling:
        anti_patterns.append(
            GuidanceItem(
                "ANTI_SWALLOW_ERRORS",
                "Do not swallow RAISERROR/THROW; map to exceptions and rollback.",
            )
        )

    if complexity > 8:
        confidence -= 0.05
    if has_dynamic_sql or has_cursor or uses_temp_objects:
        confidence -= 0.05
    if uses_transaction_in_sql:
        confidence -= 0.15

    confidence = _clamp(confidence, 0.5, 0.9)

    suggestions_payload = _normalize_guidance(suggestions)
    anti_patterns_payload = _normalize_guidance(anti_patterns)
    notes_payload = list(notes)
    (
        suggestions_payload,
        anti_patterns_payload,
        notes_payload,
        truncation_error,
    ) = _apply_max_items(suggestions_payload, anti_patterns_payload, notes_payload, max_items)

    errors: list[str] = []
    if truncation_error:
        errors.append(truncation_error)

    java_snippets = {
        "annotation_example": _annotation_example(recommended_boundary),
        "notes": notes_payload,
    }

    return {
        "version": "3.2.0",
        "summary": {
            "recommended_boundary": recommended_boundary,
            "transactional": transactional,
            "propagation": propagation,
            "isolation_level": summary_isolation,
            "read_only": read_only,
            "confidence": confidence,
        },
        "signals": {
            "has_writes": has_writes,
            "write_ops": write_ops,
            "uses_transaction_in_sql": uses_transaction_in_sql,
            "begin_count": transactions["begin_count"],
            "commit_count": transactions["commit_count"],
            "rollback_count": transactions["rollback_count"],
            "has_try_catch": has_try_catch,
            "xact_abort": xact_abort,
            "isolation_level_in_sql": isolation_level_in_sql,
            "has_dynamic_sql": has_dynamic_sql,
            "has_cursor": has_cursor,
            "uses_temp_objects": uses_temp_objects,
            "cyclomatic_complexity": complexity,
            "error_signaling": error_signaling,
        },
        "suggestions": suggestions_payload,
        "anti_patterns": anti_patterns_payload,
        "java_snippets": java_snippets,
        "errors": errors,
    }


# [함수 설명]
# - 목적: _write_ops 처리 로직을 수행한다.
# - 입력: operations: dict[str, dict[str, object]]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _write_ops(operations: dict[str, dict[str, object]]) -> list[str]:
    ordered_ops = ["insert", "update", "delete", "merge", "truncate", "select_into"]
    return [op for op in ordered_ops if operations[op]["count"] > 0]


# [함수 설명]
# - 목적: _error_signaling 처리 로직을 수행한다.
# - 입력: error_handling: dict[str, object]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: _normalize_isolation_level 처리 로직을 수행한다.
# - 입력: value: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _normalize_isolation_level(value: str) -> str:
    normalized = " ".join(value.upper().split())
    mapping = {
        "READ UNCOMMITTED": "READ_UNCOMMITTED",
        "READ COMMITTED": "READ_COMMITTED",
        "REPEATABLE READ": "REPEATABLE_READ",
        "SNAPSHOT": "SNAPSHOT",
        "SERIALIZABLE": "SERIALIZABLE",
    }
    return mapping.get(normalized, normalized.replace(" ", "_"))


# [함수 설명]
# - 목적: _normalize_guidance 처리 로직을 수행한다.
# - 입력: items: list[GuidanceItem]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _normalize_guidance(items: list[GuidanceItem]) -> list[dict[str, str]]:
    by_id: dict[str, GuidanceItem] = {}
    for item in items:
        if item.id in by_id:
            continue
        by_id[item.id] = item
    return [
        {"id": item.id, "message": item.message}
        for item in sorted(by_id.values(), key=lambda item: item.id)
    ]


# [함수 설명]
# - 목적: _apply_max_items 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _apply_max_items(
    suggestions: list[dict[str, str]],
    anti_patterns: list[dict[str, str]],
    notes: list[str],
    max_items: int,
) -> tuple[list[dict[str, str]], list[dict[str, str]], list[str], str | None]:
    if max_items <= 0:
        return [], [], [], "max_items_exceeded: truncated suggestions/anti_patterns/notes"

    total = len(suggestions) + len(anti_patterns) + len(notes)
    if total <= max_items:
        return suggestions, anti_patterns, notes, None

    remaining = max_items
    trimmed_suggestions = suggestions[:remaining]
    remaining -= len(trimmed_suggestions)

    trimmed_anti_patterns = anti_patterns[: max(0, remaining)]
    remaining -= len(trimmed_anti_patterns)

    trimmed_notes = notes[: max(0, remaining)]

    return (
        trimmed_suggestions,
        trimmed_anti_patterns,
        trimmed_notes,
        "max_items_exceeded: truncated suggestions/anti_patterns/notes",
    )


# [함수 설명]
# - 목적: _annotation_example 처리 로직을 수행한다.
# - 입력: boundary: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _annotation_example(boundary: str) -> str:
    if boundary == "service_layer":
        return "@Transactional(propagation = Propagation.REQUIRED)"
    if boundary == "hybrid":
        return "@Transactional(propagation = Propagation.NOT_SUPPORTED)"
    return ""


# [함수 설명]
# - 목적: _clamp 처리 로직을 수행한다.
# - 입력: value: float, lower: float, upper: float
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))

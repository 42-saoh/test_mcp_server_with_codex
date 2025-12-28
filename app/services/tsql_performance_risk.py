# [파일 설명]
# - 목적: T-SQL 분석/추천 로직을 제공하는 서비스 모듈이다.
# - 제공 기능: 분석 결과 요약, 위험도 평가, 전략 추천 등의 함수를 포함한다.
# - 입력/출력: SQL 또는 옵션을 입력받아 구조화된 dict 결과를 반환한다.
# - 주의 사항: 원문 SQL은 요약/해시로만 다루며 직접 노출하지 않는다.
# - 연관 모듈: app.api.mcp 라우터에서 호출된다.
from __future__ import annotations

import logging
import re
from typing import Any

from app.services.safe_sql import summarize_sql

logger = logging.getLogger(__name__)

try:  # pragma: no cover - optional dependency
    from sqlglot import exp, parse

    SQLGLOT_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    SQLGLOT_AVAILABLE = False


SEVERITY_ORDER = {
    "critical": 0,
    "high": 1,
    "medium": 2,
    "low": 3,
}
SEVERITY_POINTS = {
    "critical": 30,
    "high": 20,
    "medium": 10,
    "low": 5,
}
SEVERITY_CAPS = {
    "critical": 60,
    "high": 60,
    "medium": 40,
    "low": 20,
}


RECOMMENDATION_MAP = {
    "PRF_SELECT_STAR": (
        "REC_AVOID_SELECT_STAR",
        "Replace SELECT * with explicit columns to reduce I/O and improve plan stability.",
    ),
    "PRF_LEADING_WILDCARD_LIKE": (
        "REC_REWRITE_LIKE_PATTERN",
        "Avoid leading wildcards in LIKE patterns to keep predicates sargable.",
    ),
    "PRF_FUNCTION_ON_COLUMN": (
        "REC_MAKE_PREDICATES_SARGABLE",
        "Avoid wrapping columns in functions inside predicates to preserve index usage.",
    ),
    "PRF_CURSOR_RBAR": (
        "REC_REPLACE_CURSOR_SET_BASED",
        "Replace cursor logic with set-based operations for better performance.",
    ),
    "PRF_NOLOCK": (
        "REC_REVIEW_NOLOCK_USAGE",
        "Review NOLOCK usage to avoid dirty reads unless explicitly acceptable.",
    ),
    "PRF_NO_WHERE_ON_UPDATE": (
        "REC_ADD_UPDATE_WHERE",
        "Ensure UPDATE statements include appropriate predicates to avoid full-table writes.",
    ),
    "PRF_NO_WHERE_ON_DELETE": (
        "REC_ADD_DELETE_WHERE",
        "Ensure DELETE statements include appropriate predicates to avoid full-table deletes.",
    ),
    "PRF_POSSIBLE_NO_WHERE_UPDATE": (
        "REC_REVIEW_UPDATE_PREDICATE",
        "Review UPDATE predicates to confirm the scope is intentional.",
    ),
    "PRF_POSSIBLE_NO_WHERE_DELETE": (
        "REC_REVIEW_DELETE_PREDICATE",
        "Review DELETE predicates to confirm the scope is intentional.",
    ),
    "PRF_DYNAMIC_SQL": (
        "REC_PARAMETERIZE_DYNAMIC_SQL",
        "Prefer parameterized statements over dynamic SQL to improve plan reuse.",
    ),
    "PRF_LOOP_RBAR": (
        "REC_BATCH_SET_BASED",
        "Refactor row-by-row loops to set-based operations when possible.",
    ),
    "PRF_SELECT_INTO": (
        "REC_REVIEW_SELECT_INTO",
        "Consider alternatives to SELECT INTO to control logging and tempdb usage.",
    ),
    "PRF_MERGE": (
        "REC_REVIEW_MERGE",
        "Review MERGE usage for concurrency and plan stability considerations.",
    ),
    "PRF_IMPLICIT_CONVERSION_HINT": (
        "REC_AVOID_IMPLICIT_CONVERSION",
        "Align data types to avoid implicit conversions in predicates.",
    ),
    "PRF_OR_CHAIN": (
        "REC_SIMPLIFY_OR_CHAINS",
        "Simplify large OR chains or consider alternative predicate strategies.",
    ),
    "PRF_IN_LIST_LARGE": (
        "REC_REVIEW_LARGE_IN_LIST",
        "Consider temp tables or table-valued parameters for large IN lists.",
    ),
    "PRF_SCALAR_UDF": (
        "REC_REWRITE_SCALAR_UDF",
        "Review scalar UDF usage and consider inline alternatives.",
    ),
    "PRF_TABLE_VARIABLE": (
        "REC_REVIEW_TABLE_VARIABLE",
        "Review table variable usage for cardinality estimation impacts.",
    ),
    "PRF_TEMP_TABLE": (
        "REC_REVIEW_TEMP_TABLE",
        "Review temp table usage to avoid unnecessary tempdb pressure.",
    ),
    "PRF_ORDER_BY_NO_TOP": (
        "REC_REVIEW_ORDER_BY",
        "Review ORDER BY usage when no TOP/OFFSET is present.",
    ),
}


# [함수 설명]
# - 목적: analyze_performance_risk 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 주요 키는 summary, signals, findings, errors이다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def analyze_performance_risk(
    sql: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    max_findings: int = 50,
) -> dict[str, Any]:
    summary = summarize_sql(sql)
    logger.info(
        "analyze_performance_risk: sql_len=%s sql_hash=%s",
        summary["len"],
        summary["sha256_8"],
    )

    stripped_sql = _strip_comments(sql)
    wildcard_like = _detect_leading_wildcard_like(stripped_sql)
    large_in_list = _detect_large_in_list(stripped_sql)

    masked_sql = _mask_string_literals(stripped_sql)
    normalized_sql = _normalize_whitespace(masked_sql)
    scan_sql = normalized_sql.upper() if case_insensitive else normalized_sql

    findings: list[dict[str, Any]] = []
    errors: list[str] = []
    seen_findings: set[str] = set()

    # [함수 설명]
    # - 목적: add_finding 처리 로직을 수행한다.
    # - 입력: 함수 시그니처 인자
    # - 출력: 구조화된 dict 결과를 반환한다.
    # - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
    # - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
    # - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
    def add_finding(
        finding_id: str,
        severity: str,
        title: str,
        markers: list[str],
        recommendation: str,
    ) -> None:
        if finding_id in seen_findings:
            return
        seen_findings.add(finding_id)
        findings.append(
            {
                "id": finding_id,
                "severity": severity,
                "title": title,
                "markers": markers,
                "recommendation": recommendation,
            }
        )

    if _has_cursor(scan_sql):
        add_finding(
            "PRF_CURSOR_RBAR",
            "critical",
            "Cursor usage detected",
            ["CURSOR"],
            "Rewrite cursor logic to set-based operations where possible.",
        )

    if _has_loop_dml(scan_sql):
        add_finding(
            "PRF_LOOP_RBAR",
            "high",
            "Row-by-row loop with DML detected",
            ["WHILE", "DML_IN_LOOP"],
            "Refactor WHILE loops that perform DML into set-based operations.",
        )

    if _has_dynamic_sql(scan_sql):
        add_finding(
            "PRF_DYNAMIC_SQL",
            "high",
            "Dynamic SQL detected",
            ["SP_EXECUTESQL", "EXEC(@)"],
            "Prefer parameterized statements over dynamic SQL for plan stability.",
        )

    update_where_status = _detect_missing_where(
        normalized_sql,
        scan_sql,
        dialect,
        "update",
        errors,
    )
    if update_where_status == "missing":
        add_finding(
            "PRF_NO_WHERE_ON_UPDATE",
            "high",
            "UPDATE without WHERE detected",
            ["UPDATE", "NO_WHERE"],
            "Ensure write statements have appropriate predicates to avoid full-table operations.",
        )
    elif update_where_status == "possible":
        add_finding(
            "PRF_POSSIBLE_NO_WHERE_UPDATE",
            "medium",
            "Possible UPDATE without WHERE detected",
            ["UPDATE", "POSSIBLE_NO_WHERE"],
            "Review UPDATE statements to confirm predicates are present.",
        )

    delete_where_status = _detect_missing_where(
        normalized_sql,
        scan_sql,
        dialect,
        "delete",
        errors,
    )
    if delete_where_status == "missing":
        add_finding(
            "PRF_NO_WHERE_ON_DELETE",
            "high",
            "DELETE without WHERE detected",
            ["DELETE", "NO_WHERE"],
            "Ensure write statements have appropriate predicates to avoid full-table operations.",
        )
    elif delete_where_status == "possible":
        add_finding(
            "PRF_POSSIBLE_NO_WHERE_DELETE",
            "medium",
            "Possible DELETE without WHERE detected",
            ["DELETE", "POSSIBLE_NO_WHERE"],
            "Review DELETE statements to confirm predicates are present.",
        )

    if _detect_select_into(scan_sql):
        add_finding(
            "PRF_SELECT_INTO",
            "high",
            "SELECT INTO detected",
            ["SELECT", "INTO"],
            "Review SELECT INTO usage to avoid unexpected logging or tempdb pressure.",
        )

    if _detect_merge(scan_sql):
        add_finding(
            "PRF_MERGE",
            "high",
            "MERGE statement detected",
            ["MERGE"],
            "Review MERGE usage for concurrency and plan stability impacts.",
        )

    if _detect_select_star(scan_sql):
        add_finding(
            "PRF_SELECT_STAR",
            "medium",
            "SELECT * usage detected",
            ["SELECT", "*"],
            "Replace SELECT * with explicit columns to reduce I/O and improve plan stability.",
        )

    if wildcard_like:
        add_finding(
            "PRF_LEADING_WILDCARD_LIKE",
            "medium",
            "Leading wildcard LIKE detected",
            ["LIKE", "LEADING_WILDCARD"],
            "Avoid leading wildcards in LIKE patterns to keep predicates sargable.",
        )

    if _detect_function_on_column(scan_sql):
        add_finding(
            "PRF_FUNCTION_ON_COLUMN",
            "medium",
            "Function applied to predicate column detected",
            ["FUNCTION_ON_PREDICATE"],
            "Avoid wrapping columns in functions inside predicates to preserve index usage.",
        )

    if _detect_implicit_conversion(scan_sql):
        add_finding(
            "PRF_IMPLICIT_CONVERSION_HINT",
            "medium",
            "Possible implicit conversion detected",
            ["IMPLICIT_CONVERSION_RISK"],
            "Align data types to avoid implicit conversions in predicates.",
        )

    if _detect_or_chain(scan_sql):
        add_finding(
            "PRF_OR_CHAIN",
            "medium",
            "Long OR chain in WHERE detected",
            ["MANY_OR"],
            "Simplify large OR chains or consider alternative predicate strategies.",
        )

    if large_in_list:
        add_finding(
            "PRF_IN_LIST_LARGE",
            "medium",
            "Large IN list detected",
            ["LARGE_IN_LIST"],
            "Consider temp tables or table-valued parameters for large IN lists.",
        )

    if _detect_scalar_udf(scan_sql):
        add_finding(
            "PRF_SCALAR_UDF",
            "medium",
            "Scalar UDF call detected",
            ["SCALAR_UDF_CALL"],
            "Review scalar UDF usage and consider inline alternatives.",
        )

    if _detect_nolock(scan_sql):
        add_finding(
            "PRF_NOLOCK",
            "low",
            "NOLOCK hint detected",
            ["NOLOCK"],
            "Review NOLOCK usage to avoid dirty reads unless explicitly acceptable.",
        )

    if _detect_table_variable(scan_sql):
        add_finding(
            "PRF_TABLE_VARIABLE",
            "low",
            "Table variable usage detected",
            ["TABLE_VARIABLE"],
            "Review table variable usage for cardinality estimation impacts.",
        )

    if _detect_temp_table(scan_sql):
        add_finding(
            "PRF_TEMP_TABLE",
            "low",
            "Temporary table usage detected",
            ["TEMP_TABLE"],
            "Review temp table usage to avoid unnecessary tempdb pressure.",
        )

    if _detect_order_by_no_top(scan_sql):
        add_finding(
            "PRF_ORDER_BY_NO_TOP",
            "low",
            "ORDER BY without TOP/OFFSET detected",
            ["ORDER_BY"],
            "Review ORDER BY usage when no TOP/OFFSET is present.",
        )

    findings = sorted(
        findings,
        key=lambda item: (SEVERITY_ORDER[item["severity"]], item["id"]),
    )

    truncated = False
    if len(findings) > max_findings:
        findings = findings[:max_findings]
        truncated = True
        errors.append(f"findings_truncated: max_findings={max_findings}")

    signals = _build_signals(sql, dialect)
    recommendations = _build_recommendations(findings)

    return {
        "version": "4.1.0",
        "summary": _build_summary(findings, truncated, signals["cyclomatic_complexity"]),
        "signals": signals,
        "findings": findings,
        "recommendations": recommendations,
        "errors": errors,
    }


# [함수 설명]
# - 목적: _build_summary 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_summary(
    findings: list[dict[str, Any]],
    truncated: bool,
    cyclomatic_complexity: int,
) -> dict[str, Any]:
    severity_counts: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for item in findings:
        severity_counts[item["severity"]] += 1

    risk_score = _calculate_risk_score(severity_counts, cyclomatic_complexity)
    risk_level = _risk_level(risk_score)

    return {
        "risk_score": risk_score,
        "risk_level": risk_level,
        "finding_count": len(findings),
        "truncated": truncated,
    }


# [함수 설명]
# - 목적: _build_signals 처리 로직을 수행한다.
# - 입력: sql: str, dialect: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_signals(sql: str, dialect: str) -> dict[str, Any]:
    from app.services.tsql_analyzer import (
        analyze_control_flow,
        analyze_data_changes,
        analyze_migration_impacts,
        analyze_references,
        analyze_transactions,
    )

    references = analyze_references(sql, dialect)
    transactions = analyze_transactions(sql)
    control_flow = analyze_control_flow(sql, dialect)
    data_changes = analyze_data_changes(sql, dialect)
    impacts = analyze_migration_impacts(sql)

    items = impacts.get("items", [])
    impact_ids = {item.get("id") for item in items}

    return {
        "table_count": len(references.get("references", {}).get("tables", [])),
        "has_writes": bool(data_changes.get("data_changes", {}).get("has_writes")),
        "uses_transaction": bool(transactions.get("uses_transaction")),
        "cyclomatic_complexity": control_flow.get("control_flow", {})
        .get("summary", {})
        .get("cyclomatic_complexity", 1),
        "has_cursor": "IMP_CURSOR" in impact_ids,
        "has_dynamic_sql": "IMP_DYN_SQL" in impact_ids,
    }


# [함수 설명]
# - 목적: _build_recommendations 처리 로직을 수행한다.
# - 입력: findings: list[dict[str, Any]]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_recommendations(findings: list[dict[str, Any]]) -> list[dict[str, str]]:
    recommendations: dict[str, str] = {}
    for item in findings:
        rec = RECOMMENDATION_MAP.get(item["id"])
        if not rec:
            continue
        rec_id, message = rec
        recommendations.setdefault(rec_id, message)

    return [
        {"id": rec_id, "message": recommendations[rec_id]} for rec_id in sorted(recommendations)
    ]


# [함수 설명]
# - 목적: _calculate_risk_score 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _calculate_risk_score(
    severity_counts: dict[str, int],
    cyclomatic_complexity: int,
) -> int:
    score = 0
    for severity, count in severity_counts.items():
        points = SEVERITY_POINTS[severity]
        cap = SEVERITY_CAPS[severity]
        score += min(count * points, cap)

    if cyclomatic_complexity > 8:
        score += 5

    return max(0, min(100, score))


# [함수 설명]
# - 목적: _risk_level 처리 로직을 수행한다.
# - 입력: score: int
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _risk_level(score: int) -> str:
    if score >= 75:
        return "critical"
    if score >= 50:
        return "high"
    if score >= 25:
        return "medium"
    return "low"


# [함수 설명]
# - 목적: _strip_comments 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _strip_comments(sql: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", without_block)


# [함수 설명]
# - 목적: _mask_string_literals 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _mask_string_literals(sql: str) -> str:
    return re.sub(r"'(?:''|[^'])*'", "''", sql)


# [함수 설명]
# - 목적: _normalize_whitespace 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _normalize_whitespace(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


# [함수 설명]
# - 목적: _detect_leading_wildcard_like 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_leading_wildcard_like(sql: str) -> bool:
    return bool(re.search(r"\bLIKE\s+N?'\s*%", sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_large_in_list 처리 로직을 수행한다.
# - 입력: sql: str, threshold: int = 20
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_large_in_list(sql: str, threshold: int = 20) -> bool:
    for match in re.finditer(r"\bIN\s*\(([^)]*)\)", sql, flags=re.IGNORECASE | re.DOTALL):
        content = match.group(1)
        if re.search(r"\bSELECT\b", content, flags=re.IGNORECASE):
            continue
        items = [item.strip() for item in content.split(",") if item.strip()]
        if len(items) >= threshold:
            return True
    return False


# [함수 설명]
# - 목적: _detect_missing_where 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_missing_where(
    normalized_sql: str,
    scan_sql: str,
    dialect: str,
    statement_type: str,
    errors: list[str],
) -> str:
    if SQLGLOT_AVAILABLE:
        try:
            expressions = parse(normalized_sql, read=dialect)
            for expression in expressions:
                if statement_type == "update":
                    for node in expression.find_all(exp.Update):
                        if node.args.get("where") is None:
                            return "missing"
                if statement_type == "delete":
                    for node in expression.find_all(exp.Delete):
                        if node.args.get("where") is None:
                            return "missing"
            return "present"
        except Exception as exc:  # pragma: no cover - parse fallback
            errors.append(f"parse_error: {exc.__class__.__name__}")

    statement_pattern = (
        r"\bUPDATE\b[\s\S]*?(?:;|$)" if statement_type == "update" else r"\bDELETE\b[\s\S]*?(?:;|$)"
    )
    for match in re.finditer(statement_pattern, scan_sql, flags=re.IGNORECASE):
        statement = match.group(0)
        if " WHERE " not in statement.upper():
            return "possible"
    return "present"


# [함수 설명]
# - 목적: _has_cursor 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _has_cursor(scan_sql: str) -> bool:
    return bool(re.search(r"\bCURSOR\b", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _has_loop_dml 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _has_loop_dml(scan_sql: str) -> bool:
    for match in re.finditer(r"\bWHILE\b", scan_sql, flags=re.IGNORECASE):
        window = scan_sql[match.end() : match.end() + 300]
        if re.search(r"\b(INSERT|UPDATE|DELETE)\b", window, flags=re.IGNORECASE):
            return True
    return False


# [함수 설명]
# - 목적: _has_dynamic_sql 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _has_dynamic_sql(scan_sql: str) -> bool:
    if re.search(r"\bSP_EXECUTESQL\b", scan_sql, flags=re.IGNORECASE):
        return True
    return bool(re.search(r"\bEXEC(?:UTE)?\s*\(?\s*@\w+", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_select_into 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_select_into(scan_sql: str) -> bool:
    return bool(re.search(r"\bSELECT\b[\s\S]*?\bINTO\b", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_merge 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_merge(scan_sql: str) -> bool:
    return bool(re.search(r"\bMERGE\b", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_select_star 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_select_star(scan_sql: str) -> bool:
    return bool(re.search(r"\bSELECT\s+(?:TOP\s+\d+\s+)?\*", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_function_on_column 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_function_on_column(scan_sql: str) -> bool:
    return bool(
        re.search(
            r"\bWHERE\b[\s\S]*?\b(UPPER|LOWER|CONVERT|CAST)\s*\(",
            scan_sql,
            flags=re.IGNORECASE,
        )
    )


# [함수 설명]
# - 목적: _detect_implicit_conversion 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_implicit_conversion(scan_sql: str) -> bool:
    return bool(
        re.search(
            r"\bWHERE\b[\s\S]*?\b(CAST|CONVERT)\s*\([^\)]*\)\s*[=<>]",
            scan_sql,
            flags=re.IGNORECASE,
        )
    )


# [함수 설명]
# - 목적: _detect_or_chain 처리 로직을 수행한다.
# - 입력: scan_sql: str, threshold: int = 5
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_or_chain(scan_sql: str, threshold: int = 5) -> bool:
    for match in re.finditer(
        r"\bWHERE\b([\s\S]*?)(?:\bGROUP\b|\bORDER\b|\bHAVING\b|\bUNION\b|;|$)",
        scan_sql,
        flags=re.IGNORECASE,
    ):
        segment = match.group(1)
        if len(re.findall(r"\bOR\b", segment, flags=re.IGNORECASE)) >= threshold:
            return True
    return False


# [함수 설명]
# - 목적: _detect_scalar_udf 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_scalar_udf(scan_sql: str) -> bool:
    return bool(re.search(r"\b(?:\w+\.)?fn_[A-Za-z0-9_]+\s*\(", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_nolock 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_nolock(scan_sql: str) -> bool:
    return bool(re.search(r"\bNOLOCK\b", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_table_variable 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_table_variable(scan_sql: str) -> bool:
    return bool(re.search(r"\bDECLARE\s+@\w+\s+TABLE\b", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_temp_table 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_temp_table(scan_sql: str) -> bool:
    return bool(re.search(r"\B##?\w+", scan_sql, flags=re.IGNORECASE))


# [함수 설명]
# - 목적: _detect_order_by_no_top 처리 로직을 수행한다.
# - 입력: scan_sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_order_by_no_top(scan_sql: str) -> bool:
    for statement in scan_sql.split(";"):
        if "ORDER BY" in statement.upper() and " TOP " not in statement.upper():
            if " OFFSET " not in statement.upper() and " FETCH " not in statement.upper():
                return True
    return False

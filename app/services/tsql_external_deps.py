# [파일 설명]
# - 목적: T-SQL 분석/추천 로직을 제공하는 서비스 모듈이다.
# - 제공 기능: 분석 결과 요약, 위험도 평가, 전략 추천 등의 함수를 포함한다.
# - 입력/출력: SQL 또는 옵션을 입력받아 구조화된 dict 결과를 반환한다.
# - 주의 사항: 원문 SQL은 요약/해시로만 다루며 직접 노출하지 않는다.
# - 연관 모듈: app.api.mcp 라우터에서 호출된다.
from __future__ import annotations

import logging
import re
from collections.abc import Iterable

from app.services.safe_sql import summarize_sql

logger = logging.getLogger(__name__)

BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_PATTERN = re.compile(r"--.*?$", re.MULTILINE)
STRING_LITERAL_PATTERN = re.compile(r"N'(?:''|[^'])*'|'(?:''|[^'])*'", re.DOTALL)

IDENTIFIER_PATTERN = r"(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)"

SIGNAL_LIMIT = 15

EXCLUDED_DB_NAMES = {"dbo", "sys", "information_schema"}


# [함수 설명]
# - 목적: analyze_external_dependencies 처리 로직을 수행한다.
# - 입력: sql: str, options: dict | None = None
# - 출력: 주요 키는 summary, external_dependencies, signals, errors이다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def analyze_external_dependencies(sql: str, options: dict | None = None) -> dict[str, object]:
    resolved_options = _resolve_options(options)
    case_insensitive = resolved_options["case_insensitive"]
    max_items = resolved_options["max_items"]

    summary = summarize_sql(sql)
    logger.info(
        "analyze_external_dependencies: sql_len=%s sql_hash=%s",
        summary["len"],
        summary["sha256_8"],
    )

    errors: list[str] = []
    signals: set[str] = set()

    comment_stripped = _strip_comments(sql)
    clr_signals = _detect_clr_signals(comment_stripped, case_insensitive)

    cleaned_sql = _replace_string_literals(comment_stripped)

    linked_servers: dict[str, set[str]] = {}
    cross_database: set[tuple[str, str, str, str]] = set()
    remote_exec: dict[str, set[str]] = {}
    openquery: dict[str, set[str]] = {}
    opendatasource: dict[str, set[str]] = {}
    others: dict[str, set[str]] = {}

    patterns = _build_patterns(case_insensitive)

    for match in patterns["openquery"].finditer(cleaned_sql):
        server = _clean_identifier(match.group("server"))
        _add_signal(openquery, server, "OPENQUERY")
        _add_signal(linked_servers, server, "OPENQUERY")
        signals.add("OPENQUERY")

    if patterns["opendatasource"].search(cleaned_sql):
        _add_signal(opendatasource, "OPENDATASOURCE", "OPENDATASOURCE")
        signals.add("OPENDATASOURCE")

    for match in patterns["exec_at"].finditer(cleaned_sql):
        server = _clean_identifier(match.group("server"))
        _add_signal(remote_exec, server, "EXEC AT")
        _add_signal(linked_servers, server, "EXEC AT")
        signals.add("EXEC AT")

    four_part_spans: list[tuple[int, int]] = []
    for match in patterns["four_part"].finditer(cleaned_sql):
        four_part_spans.append(match.span())
        server = _clean_identifier(match.group("server"))
        _add_signal(linked_servers, server, "four_part_name")
        signals.add("four_part_name")

    for match in patterns["three_part"].finditer(cleaned_sql):
        span = match.span()
        if _span_within(span, four_part_spans):
            continue
        database = _clean_identifier(match.group("database"))
        if database.lower() in EXCLUDED_DB_NAMES:
            continue
        schema = _clean_identifier(match.group("schema"))
        obj = _clean_identifier(match.group("object"))
        cross_database.add((database, schema, obj, "three_part_name"))
        signals.add("three_part_name")

    if clr_signals:
        others["EXT_CLR"] = set(clr_signals)
        signals.add("CLR")

    if patterns["xp_cmdshell"].search(cleaned_sql):
        others["EXT_XP_CMDSHELL"] = {"XP_CMDSHELL"}
        signals.add("XP_CMDSHELL")

    linked_servers_list = _build_linked_server_list(linked_servers)
    cross_database_list = _build_cross_database_list(cross_database)
    remote_exec_list = _build_target_list(remote_exec, "exec_at")
    openquery_list = _build_target_list(openquery, "openquery")
    opendatasource_list = _build_target_list(opendatasource, "opendatasource")
    others_list = _build_other_list(others)

    linked_servers_list = _apply_limit(linked_servers_list, max_items, errors, "linked_servers")
    cross_database_list = _apply_limit(cross_database_list, max_items, errors, "cross_database")
    remote_exec_list = _apply_limit(remote_exec_list, max_items, errors, "remote_exec")
    openquery_list = _apply_limit(openquery_list, max_items, errors, "openquery")
    opendatasource_list = _apply_limit(opendatasource_list, max_items, errors, "opendatasource")
    others_list = _apply_limit(others_list, max_items, errors, "others")

    summary = {
        "has_external_deps": any(
            [
                linked_servers_list,
                cross_database_list,
                remote_exec_list,
                openquery_list,
                opendatasource_list,
                others_list,
            ]
        ),
        "linked_server_count": len(linked_servers_list),
        "cross_db_count": len(cross_database_list),
        "remote_exec_count": len(remote_exec_list),
        "openquery_count": len(openquery_list),
        "opendatasource_count": len(opendatasource_list),
    }

    return {
        "version": "2.2.0",
        "object": {
            "name": resolved_options["name"],
            "type": resolved_options["type"],
        },
        "summary": summary,
        "external_dependencies": {
            "linked_servers": linked_servers_list,
            "cross_database": cross_database_list,
            "remote_exec": remote_exec_list,
            "openquery": openquery_list,
            "opendatasource": opendatasource_list,
            "others": others_list,
        },
        "signals": _sorted_unique(signals)[:SIGNAL_LIMIT],
        "errors": errors,
    }


# [함수 설명]
# - 목적: _resolve_options 처리 로직을 수행한다.
# - 입력: options: dict | None
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _resolve_options(options: dict | None) -> dict[str, object]:
    resolved = {"case_insensitive": True, "max_items": 200, "name": "", "type": ""}
    if options:
        resolved.update({k: v for k, v in options.items() if v is not None})
    return resolved


# [함수 설명]
# - 목적: _build_patterns 처리 로직을 수행한다.
# - 입력: case_insensitive: bool
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_patterns(case_insensitive: bool) -> dict[str, re.Pattern[str]]:
    flags = re.IGNORECASE if case_insensitive else 0
    return {
        "openquery": re.compile(rf"\bOPENQUERY\s*\(\s*(?P<server>{IDENTIFIER_PATTERN})\s*,", flags),
        "opendatasource": re.compile(r"\bOPENDATASOURCE\s*\(", flags),
        "exec_at": re.compile(
            rf"\bEXEC(?:UTE)?\b[^;]*?\bAT\b\s*(?P<server>{IDENTIFIER_PATTERN})",
            flags,
        ),
        "four_part": re.compile(
            rf"\b(?P<server>{IDENTIFIER_PATTERN})\s*\.\s*(?P<database>{IDENTIFIER_PATTERN})"
            rf"\s*\.\s*(?P<schema>{IDENTIFIER_PATTERN})\s*\.\s*(?P<object>{IDENTIFIER_PATTERN})\b",
            flags,
        ),
        "three_part": re.compile(
            rf"\b(?P<database>{IDENTIFIER_PATTERN})\s*\.\s*(?P<schema>{IDENTIFIER_PATTERN})"
            rf"\s*\.\s*(?P<object>{IDENTIFIER_PATTERN})\b",
            flags,
        ),
        "xp_cmdshell": re.compile(r"\bxp_cmdshell\b", flags),
    }


# [함수 설명]
# - 목적: _strip_comments 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _strip_comments(sql: str) -> str:
    sql = BLOCK_COMMENT_PATTERN.sub(" ", sql)
    return LINE_COMMENT_PATTERN.sub(" ", sql)


# [함수 설명]
# - 목적: _replace_string_literals 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _replace_string_literals(sql: str) -> str:
    return STRING_LITERAL_PATTERN.sub("''", sql)


# [함수 설명]
# - 목적: _detect_clr_signals 처리 로직을 수행한다.
# - 입력: sql: str, case_insensitive: bool
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _detect_clr_signals(sql: str, case_insensitive: bool) -> list[str]:
    flags = re.IGNORECASE if case_insensitive else 0
    signals: set[str] = set()

    if re.search(r"\bCREATE\s+ASSEMBLY\b", sql, flags):
        signals.update(["CLR", "CREATE ASSEMBLY"])
    if re.search(r"\bEXTERNAL_ACCESS\b", sql, flags):
        signals.update(["CLR", "EXTERNAL_ACCESS"])
    if re.search(r"\bUNSAFE\b", sql, flags):
        signals.update(["CLR", "UNSAFE"])
    if re.search(r"\bsp_configure\b\s*N?'[^']*clr\s+enabled[^']*'", sql, flags):
        signals.update(["CLR", "CLR_ENABLED"])

    return _sorted_unique(signals)


# [함수 설명]
# - 목적: _clean_identifier 처리 로직을 수행한다.
# - 입력: identifier: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _clean_identifier(identifier: str) -> str:
    identifier = identifier.strip()
    if identifier.startswith("[") and identifier.endswith("]"):
        return identifier[1:-1]
    return identifier


# [함수 설명]
# - 목적: _add_signal 처리 로직을 수행한다.
# - 입력: targets: dict[str, set[str]], name: str, signal: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _add_signal(targets: dict[str, set[str]], name: str, signal: str) -> None:
    if not name:
        return
    targets.setdefault(name, set()).add(signal)


# [함수 설명]
# - 목적: _build_linked_server_list 처리 로직을 수행한다.
# - 입력: linked_servers: dict[str, set[str]]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_linked_server_list(linked_servers: dict[str, set[str]]) -> list[dict[str, object]]:
    items = [
        {"name": name, "signals": _sorted_unique(signals)}
        for name, signals in linked_servers.items()
    ]
    items.sort(key=lambda item: item["name"].lower())
    return items


# [함수 설명]
# - 목적: _build_cross_database_list 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_cross_database_list(
    cross_database: Iterable[tuple[str, str, str, str]],
) -> list[dict[str, object]]:
    items = [
        {
            "database": database,
            "schema": schema,
            "object": obj,
            "kind": kind,
        }
        for database, schema, obj, kind in cross_database
    ]
    items.sort(
        key=lambda item: (
            item["database"].lower(),
            item["schema"].lower(),
            item["object"].lower(),
        )
    )
    return items


# [함수 설명]
# - 목적: _build_target_list 처리 로직을 수행한다.
# - 입력: targets: dict[str, set[str]], kind: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_target_list(targets: dict[str, set[str]], kind: str) -> list[dict[str, object]]:
    items = [
        {"target": target, "kind": kind, "signals": _sorted_unique(signals)}
        for target, signals in targets.items()
    ]
    items.sort(key=lambda item: item["target"].lower())
    return items


# [함수 설명]
# - 목적: _build_other_list 처리 로직을 수행한다.
# - 입력: others: dict[str, set[str]]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _build_other_list(others: dict[str, set[str]]) -> list[dict[str, object]]:
    items = [
        {"id": key, "kind": _infer_other_kind(key), "signals": _sorted_unique(signals)}
        for key, signals in others.items()
    ]
    items.sort(key=lambda item: item["id"].lower())
    return items


# [함수 설명]
# - 목적: _infer_other_kind 처리 로직을 수행한다.
# - 입력: key: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _infer_other_kind(key: str) -> str:
    if key == "EXT_XP_CMDSHELL":
        return "xp_cmdshell"
    return "clr"


# [함수 설명]
# - 목적: _span_within 처리 로직을 수행한다.
# - 입력: span: tuple[int, int], spans: Iterable[tuple[int, int]]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _span_within(span: tuple[int, int], spans: Iterable[tuple[int, int]]) -> bool:
    start, end = span
    return any(start >= span_start and end <= span_end for span_start, span_end in spans)


# [함수 설명]
# - 목적: _apply_limit 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _apply_limit(
    items: list[dict[str, object]], max_items: int, errors: list[str], label: str
) -> list[dict[str, object]]:
    if len(items) <= max_items:
        return items
    errors.append(f"max_items_exceeded: {label} truncated to {max_items}")
    return items[:max_items]


# [함수 설명]
# - 목적: _sorted_unique 처리 로직을 수행한다.
# - 입력: values: Iterable[str]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _sorted_unique(values: Iterable[str]) -> list[str]:
    return sorted({value for value in values if value})

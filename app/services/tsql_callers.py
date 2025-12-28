from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.safe_sql import strip_comments_and_strings, summarize_sql

logger = logging.getLogger(__name__)

MAX_OBJECTS = 500
MAX_TOTAL_SQL_LENGTH = 1_000_000
SIGNAL_LIMIT = 10

IDENTIFIER_PATTERN = r"(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)"
QUALIFIED_NAME_PATTERN = rf"{IDENTIFIER_PATTERN}(?:\s*\.\s*{IDENTIFIER_PATTERN})*"


@dataclass(frozen=True)
class SqlObject:
    name: str
    type: str
    sql: str


@dataclass(frozen=True)
class CallerOptions:
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_self: bool = False


def find_callers(
    target: str, target_type: str, objects: list[SqlObject], options: CallerOptions
) -> dict[str, object]:
    normalized_target = _normalize_full_name(target, case_insensitive=True)
    comparison_target = _normalize_full_name(target, case_insensitive=options.case_insensitive)
    target_schema, target_name = _split_identifier(
        target, case_insensitive=options.case_insensitive
    )
    errors: list[str] = []

    total_length = sum(len(obj.sql) for obj in objects)
    logger.info(
        "find_callers: target=%s objects=%s total_sql_len=%s",
        normalized_target,
        len(objects),
        total_length,
    )

    objects_to_process = _apply_limits(objects, total_length, errors)

    exec_pattern, function_pattern = _build_patterns(options.case_insensitive)
    callers: list[dict[str, object]] = []

    for sql_object in objects_to_process:
        if not options.include_self and _is_self(
            sql_object.name, comparison_target, options.case_insensitive
        ):
            continue

        cleaned_sql = strip_comments_and_strings(sql_object.sql)
        summary = summarize_sql(sql_object.sql)
        logger.info(
            "find_callers: object=%s sql_len=%s sql_hash=%s",
            sql_object.name,
            summary["len"],
            summary["sha256_8"],
        )

        matches: list[tuple[str, str]] = []
        if target_type == "function":
            matches.extend(
                _find_function_calls(
                    cleaned_sql,
                    target_schema,
                    target_name,
                    options,
                    function_pattern,
                )
            )
        else:
            matches.extend(
                _find_exec_calls(
                    cleaned_sql,
                    target_schema,
                    target_name,
                    options,
                    exec_pattern,
                )
            )

        if not matches:
            continue

        call_kinds = _ordered_unique([kind for kind, _signal in matches])
        signals = _ordered_unique([signal for _kind, signal in matches])[:SIGNAL_LIMIT]

        callers.append(
            {
                "name": sql_object.name,
                "type": sql_object.type,
                "call_count": len(matches),
                "call_kinds": call_kinds,
                "signals": signals,
            }
        )

    callers.sort(key=lambda caller: (-caller["call_count"], caller["name"].lower()))

    total_calls = sum(caller["call_count"] for caller in callers)
    summary = {
        "has_callers": total_calls > 0,
        "caller_count": len(callers),
        "total_calls": total_calls,
    }

    return {
        "version": "2.1.0",
        "target": {
            "name": target,
            "type": target_type,
            "normalized": normalized_target,
        },
        "summary": summary,
        "callers": callers,
        "errors": errors,
    }


def _apply_limits(
    objects: list[SqlObject], total_length: int, errors: list[str]
) -> list[SqlObject]:
    objects_to_process = objects[:MAX_OBJECTS]
    if len(objects) > MAX_OBJECTS:
        errors.append(
            f"object_limit_exceeded: max={MAX_OBJECTS} provided={len(objects)} "
            f"processed={len(objects_to_process)}"
        )

    if total_length > MAX_TOTAL_SQL_LENGTH:
        errors.append(
            f"sql_limit_exceeded: max_total_len={MAX_TOTAL_SQL_LENGTH} provided={total_length}"
        )

    trimmed: list[SqlObject] = []
    running_length = 0
    for sql_object in objects_to_process:
        if running_length + len(sql_object.sql) > MAX_TOTAL_SQL_LENGTH:
            break
        trimmed.append(sql_object)
        running_length += len(sql_object.sql)

    if len(trimmed) < len(objects_to_process) and total_length <= MAX_TOTAL_SQL_LENGTH:
        errors.append("sql_limit_exceeded: truncated_objects due to per-request SQL length cap")

    return trimmed


def _build_patterns(case_insensitive: bool) -> tuple[re.Pattern[str], re.Pattern[str]]:
    flags = re.IGNORECASE if case_insensitive else 0
    exec_pattern = re.compile(
        rf"\b(?P<kind>EXEC(?:UTE)?)\s+(?!\s*@)(?!\s*\()(?P<name>{QUALIFIED_NAME_PATTERN})",
        flags,
    )
    function_pattern = re.compile(rf"\b(?P<name>{QUALIFIED_NAME_PATTERN})\s*\(", flags)
    return exec_pattern, function_pattern


def _find_exec_calls(
    sql: str,
    target_schema: str | None,
    target_name: str,
    options: CallerOptions,
    exec_pattern: re.Pattern[str],
) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for match in exec_pattern.finditer(sql):
        name = match.group("name")
        if not _matches_target(name, target_schema, target_name, options):
            continue
        kind = match.group("kind").lower()
        signal = "EXECUTE" if kind == "execute" else "EXEC"
        matches.append((kind, signal))
    return matches


def _find_function_calls(
    sql: str,
    target_schema: str | None,
    target_name: str,
    options: CallerOptions,
    function_pattern: re.Pattern[str],
) -> list[tuple[str, str]]:
    matches: list[tuple[str, str]] = []
    for match in function_pattern.finditer(sql):
        name = match.group("name")
        if not _matches_target(name, target_schema, target_name, options):
            continue
        matches.append(("function_call", "FUNCTION"))
    return matches


def _matches_target(
    candidate: str, target_schema: str | None, target_name: str, options: CallerOptions
) -> bool:
    schema, name = _split_identifier(candidate, case_insensitive=options.case_insensitive)
    if options.schema_sensitive and target_schema:
        return schema == target_schema and name == target_name
    return name == target_name


def _split_identifier(name: str, case_insensitive: bool) -> tuple[str | None, str]:
    parts = [_clean_identifier(part) for part in re.split(r"\.", name) if part.strip()]
    if case_insensitive:
        parts = [part.lower() for part in parts]
    if not parts:
        return None, ""
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, parts[-1]


def _normalize_full_name(name: str, case_insensitive: bool) -> str:
    parts = [_clean_identifier(part) for part in re.split(r"\.", name) if part.strip()]
    if case_insensitive:
        parts = [part.lower() for part in parts]
    return ".".join(parts)


def _clean_identifier(part: str) -> str:
    part = part.strip()
    if part.startswith("[") and part.endswith("]") and len(part) > 1:
        return part[1:-1]
    if part.startswith('"') and part.endswith('"') and len(part) > 1:
        return part[1:-1]
    return part


def _ordered_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        ordered.append(item)
    return ordered


def _is_self(name: str, normalized_target: str, case_insensitive: bool) -> bool:
    candidate = _normalize_full_name(name, case_insensitive=case_insensitive)
    return candidate == normalized_target

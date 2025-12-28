from __future__ import annotations

import importlib.util
import logging
import re
from typing import Any

from app.services.safe_sql import summarize_sql

logger = logging.getLogger(__name__)

EXCLUDED_DB_TOKENS = {"dbo", "sys", "information_schema"}

FOUR_PART_PATTERN = re.compile(
    r"\b([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\s*\.\s*"
    r"([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\b",
    re.IGNORECASE,
)
THREE_PART_PATTERN = re.compile(
    r"\b([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\s*\.\s*([A-Za-z_][\w$#]*)\b",
    re.IGNORECASE,
)
OPENQUERY_PATTERN = re.compile(r"\bOPENQUERY\s*\(\s*([A-Za-z_][\w$#]*)\s*,", re.IGNORECASE)
OPENDATASOURCE_PATTERN = re.compile(r"\bOPENDATASOURCE\b", re.IGNORECASE)
EXEC_AT_PATTERN = re.compile(r"\bEXEC(?:UTE)?\b[^;]*?\bAT\s+([A-Za-z_][\w$#]*)", re.IGNORECASE)

XP_CMDSHELL_PATTERN = re.compile(r"\bxp_cmdshell\b", re.IGNORECASE)
XP_OTHER_PATTERN = re.compile(r"\bxp_[A-Za-z_][\w$#]*\b", re.IGNORECASE)
SP_OA_PATTERN = re.compile(r"\bsp_OA\w+\b", re.IGNORECASE)

CLR_PATTERN = re.compile(
    r"\bCREATE\s+ASSEMBLY\b|\bEXTERNAL_ACCESS\b|\bUNSAFE\b|\bCLR\s+ENABLED\b",
    re.IGNORECASE,
)

TEMP_TABLE_PATTERN = re.compile(r"\b##?[A-Za-z_][\w$#]*\b", re.IGNORECASE)
TEMP_TABLE_CREATE_PATTERN = re.compile(
    r"\bCREATE\s+TABLE\s+##?[A-Za-z_][\w$#]*\b",
    re.IGNORECASE,
)
TEMP_TABLE_INSERT_PATTERN = re.compile(
    r"\bINSERT\s+INTO\s+##?[A-Za-z_][\w$#]*\b",
    re.IGNORECASE,
)
TABLE_VARIABLE_PATTERN = re.compile(r"\bDECLARE\s+@\w+\s+TABLE\b", re.IGNORECASE)

REASON_MESSAGES = {
    "RSN_LINKED_SERVER": "Linked server usage increases environment coupling and deployment complexity.",
    "RSN_CROSS_DB": "Cross-database references increase coupling across database boundaries.",
    "RSN_REMOTE_EXEC": "Remote execution adds operational complexity and harder testing scenarios.",
    "RSN_OPENQUERY": "OPENQUERY usage introduces linked server dependency and remote execution risks.",
    "RSN_OPENDATASOURCE": "OPENDATASOURCE usage introduces ad-hoc external data source coupling.",
    "RSN_XP_CMDSHELL": "xp_cmdshell usage adds operational and security risks.",
    "RSN_SYSTEM_PROC": "System procedure usage increases dependency on SQL Server-specific features.",
    "RSN_CLR": "CLR/external access features add deployment and security complexity.",
    "RSN_TEMPDB": "Tempdb usage increases operational coupling and resource pressure.",
}

RECOMMENDATION_MAP = {
    "RSN_LINKED_SERVER": (
        "REC_REMOVE_LINKED_SERVER",
        "Replace linked server calls with application-side integration or dedicated services.",
    ),
    "RSN_CROSS_DB": (
        "REC_ISOLATE_EXTERNAL_DEPS",
        "Isolate cross-database logic behind a dedicated integration layer.",
    ),
    "RSN_REMOTE_EXEC": (
        "REC_ISOLATE_EXTERNAL_DEPS",
        "Isolate remote execution logic behind a dedicated integration layer.",
    ),
    "RSN_OPENQUERY": (
        "REC_REPLACE_OPENQUERY",
        "Replace OPENQUERY with managed integration or service calls when possible.",
    ),
    "RSN_OPENDATASOURCE": (
        "REC_ISOLATE_EXTERNAL_DEPS",
        "Avoid OPENDATASOURCE by centralizing external access in a controlled integration layer.",
    ),
    "RSN_XP_CMDSHELL": (
        "REC_REMOVE_XP_CMDSHELL",
        "Remove xp_cmdshell usage and replace with application-side orchestration.",
    ),
    "RSN_SYSTEM_PROC": (
        "REC_ISOLATE_EXTERNAL_DEPS",
        "Review system procedure usage and migrate to portable alternatives.",
    ),
    "RSN_CLR": (
        "REC_ISOLATE_EXTERNAL_DEPS",
        "Replace CLR/external access with application-side integrations.",
    ),
    "RSN_TEMPDB": (
        "REC_AVOID_TEMPDB_HOTSPOTS",
        "Limit tempdb usage by reducing temp tables or batching operations.",
    ),
}


def analyze_db_dependency(
    sql: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    schema_sensitive: bool = False,
    max_items: int = 200,
) -> dict[str, Any]:
    summary = summarize_sql(sql)
    logger.info(
        "analyze_db_dependency: sql_len=%s sql_hash=%s",
        summary["len"],
        summary["sha256_8"],
    )

    stripped_sql = _strip_comments(sql)
    masked_sql = _mask_string_literals(stripped_sql)
    normalized_sql = _normalize_whitespace(_normalize_bracketed_identifiers(masked_sql))
    scan_sql = normalized_sql

    linked_servers: dict[str, dict[str, Any]] = {}
    cross_database: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    remote_exec: dict[tuple[str, str], dict[str, Any]] = {}
    external_access: dict[str, dict[str, Any]] = {}
    system_objects: dict[str, dict[str, Any]] = {}
    tempdb_signals: dict[str, dict[str, Any]] = {}

    openquery_count = 0
    opendatasource_count = 0
    remote_exec_count = 0
    xp_cmdshell_count = 0
    system_proc_count = 0
    clr_signal_count = 0
    tempdb_pressure_signals = 0

    four_part_spans: list[tuple[int, int]] = []

    for match in FOUR_PART_PATTERN.finditer(scan_sql):
        server, db_name, schema_name, object_name = match.groups()
        server_name = _normalize_identifier(server, case_insensitive)
        four_part_spans.append(match.span())
        _add_linked_server(linked_servers, server_name, "FOUR_PART")
        _ = (db_name, schema_name, object_name)

    for match in THREE_PART_PATTERN.finditer(scan_sql):
        if _overlaps_any(match.span(), four_part_spans):
            continue
        db_name, schema_name, object_name = match.groups()
        db_token = db_name.lower() if case_insensitive else db_name
        if db_token in EXCLUDED_DB_TOKENS:
            continue
        cross_key = (
            _normalize_identifier(db_name, case_insensitive),
            _normalize_identifier(schema_name, case_insensitive)
            if schema_sensitive
            else schema_name,
            _normalize_identifier(object_name, case_insensitive),
            "three_part_name",
        )
        cross_database.setdefault(
            cross_key,
            {
                "database": cross_key[0],
                "schema": cross_key[1],
                "object": cross_key[2],
                "kind": "three_part_name",
                "signals": ["THREE_PART"],
            },
        )

    for match in OPENQUERY_PATTERN.finditer(scan_sql):
        openquery_count += 1
        server_name = _normalize_identifier(match.group(1), case_insensitive)
        _add_linked_server(linked_servers, server_name, "OPENQUERY")

    for _ in OPENDATASOURCE_PATTERN.finditer(scan_sql):
        opendatasource_count += 1

    for match in EXEC_AT_PATTERN.finditer(scan_sql):
        remote_exec_count += 1
        server_name = _normalize_identifier(match.group(1), case_insensitive)
        _add_linked_server(linked_servers, server_name, "EXEC AT")
        remote_exec.setdefault(
            (server_name, "exec_at"),
            {"target": server_name, "kind": "exec_at", "signals": ["EXEC AT"]},
        )

    xp_cmdshell_matches = XP_CMDSHELL_PATTERN.findall(scan_sql)
    if xp_cmdshell_matches:
        xp_cmdshell_count = len(xp_cmdshell_matches)
        system_objects["SYS_XP_CMDSHELL"] = {
            "id": "SYS_XP_CMDSHELL",
            "signals": ["xp_cmdshell"],
        }

    xp_other_matches = [
        match for match in XP_OTHER_PATTERN.findall(scan_sql) if match.lower() != "xp_cmdshell"
    ]
    sp_oa_matches = SP_OA_PATTERN.findall(scan_sql)
    if xp_other_matches:
        system_proc_count += len(xp_other_matches)
        system_objects["SYS_XP_OTHER"] = {"id": "SYS_XP_OTHER", "signals": ["xp_*"]}
    if sp_oa_matches:
        system_proc_count += len(sp_oa_matches)
        system_objects["SYS_OA_AUTOMATION"] = {
            "id": "SYS_OA_AUTOMATION",
            "signals": ["sp_OA*"],
        }

    clr_matches = CLR_PATTERN.findall(scan_sql)
    if clr_matches:
        clr_signal_count = len(clr_matches)
        signals = _sorted_unique(
            [
                "CLR" if "CREATE" in match.upper() else match.strip().upper().replace(" ", "_")
                for match in clr_matches
            ]
        )
        external_access["EXT_CLR"] = {"id": "EXT_CLR", "signals": signals}

    temp_table_signals: set[str] = set()
    temp_table_present = False
    if TEMP_TABLE_PATTERN.search(scan_sql):
        temp_table_present = True
        temp_table_signals.add("#temp")
    if TEMP_TABLE_CREATE_PATTERN.search(scan_sql):
        temp_table_present = True
        temp_table_signals.add("CREATE TABLE #")
    if TEMP_TABLE_INSERT_PATTERN.search(scan_sql):
        temp_table_present = True
        temp_table_signals.add("INSERT INTO #")
    if temp_table_present:
        tempdb_pressure_signals += 1
        tempdb_signals["TEMP_TABLE"] = {
            "id": "TEMP_TABLE",
            "signals": sorted(temp_table_signals),
        }

    table_variable_present = False
    if TABLE_VARIABLE_PATTERN.search(scan_sql):
        table_variable_present = True
        tempdb_pressure_signals += 1
        tempdb_signals["TABLE_VARIABLE"] = {
            "id": "TABLE_VARIABLE",
            "signals": ["TABLE_VARIABLE"],
        }

    table_count, function_call_count = _optional_reference_metrics(sql, dialect)

    unique_linked_servers = list(linked_servers.values())
    unique_cross_db = list(cross_database.values())
    unique_remote_exec = list(remote_exec.values())
    unique_external_access = list(external_access.values())
    unique_system_objects = list(system_objects.values())
    unique_tempdb_signals = list(tempdb_signals.values())

    linked_server_count = len(unique_linked_servers)
    cross_database_count = len(
        {
            item["database"].lower() if case_insensitive else item["database"]
            for item in unique_cross_db
        }
    )

    linked_server_points = _score_linked_servers(linked_server_count)
    cross_db_points = _score_cross_db(cross_database_count)
    remote_exec_points = 25 if remote_exec_count > 0 else 0
    openquery_points = 15 if openquery_count > 0 else 0
    opendatasource_points = 15 if opendatasource_count > 0 else 0
    open_source_points = min(openquery_points + opendatasource_points, 25)
    xp_cmdshell_points = 40 if xp_cmdshell_count > 0 else 0
    system_proc_points = _score_system_proc(system_proc_count)
    clr_points = 20 if clr_signal_count > 0 else 0
    tempdb_points = _score_tempdb(temp_table_present, table_variable_present)
    table_scale_points = 5 if table_count > 10 else 0

    dependency_score = min(
        100,
        linked_server_points
        + cross_db_points
        + remote_exec_points
        + open_source_points
        + xp_cmdshell_points
        + system_proc_points
        + clr_points
        + tempdb_points
        + table_scale_points,
    )

    dependency_level = _score_level(dependency_score)

    reasons: list[dict[str, Any]] = []
    if linked_server_points:
        reasons.append(_reason_item("RSN_LINKED_SERVER", linked_server_points))
    if cross_db_points:
        reasons.append(_reason_item("RSN_CROSS_DB", cross_db_points))
    if remote_exec_points:
        reasons.append(_reason_item("RSN_REMOTE_EXEC", remote_exec_points))
    if openquery_points:
        reasons.append(_reason_item("RSN_OPENQUERY", openquery_points))
    if opendatasource_points:
        reasons.append(_reason_item("RSN_OPENDATASOURCE", opendatasource_points))
    if xp_cmdshell_points:
        reasons.append(_reason_item("RSN_XP_CMDSHELL", xp_cmdshell_points))
    if system_proc_points:
        reasons.append(_reason_item("RSN_SYSTEM_PROC", system_proc_points))
    if clr_points:
        reasons.append(_reason_item("RSN_CLR", clr_points))
    if tempdb_points:
        reasons.append(_reason_item("RSN_TEMPDB", tempdb_points))

    reasons.sort(key=lambda item: (-abs(item["weight"]), item["id"]))

    recommendations: list[dict[str, str]] = []
    seen_recommendations: set[str] = set()
    for reason in reasons:
        rec = RECOMMENDATION_MAP.get(reason["id"])
        if not rec:
            continue
        rec_id, message = rec
        if rec_id in seen_recommendations:
            continue
        seen_recommendations.add(rec_id)
        recommendations.append({"id": rec_id, "message": message})
    recommendations.sort(key=lambda item: item["id"])

    dependencies = {
        "cross_database": _sort_cross_db(unique_cross_db, case_insensitive),
        "linked_servers": _sort_linked_servers(unique_linked_servers, case_insensitive),
        "remote_exec": _sort_remote_exec(unique_remote_exec, case_insensitive),
        "external_access": _sort_simple(unique_external_access),
        "system_objects": _sort_simple(unique_system_objects),
        "tempdb_signals": _sort_simple(unique_tempdb_signals),
    }

    truncated = False
    if max_items > 0:
        dependencies, truncated = _truncate_dependencies(dependencies, max_items)

    errors: list[str] = []
    if truncated:
        errors.append(f"dependency_items_truncated: max_items={max_items}")

    metrics = {
        "table_count": table_count,
        "function_call_count": function_call_count,
        "cross_database_count": cross_database_count,
        "linked_server_count": linked_server_count,
        "remote_exec_count": remote_exec_count,
        "openquery_count": openquery_count,
        "opendatasource_count": opendatasource_count,
        "system_proc_count": system_proc_count,
        "xp_cmdshell_count": xp_cmdshell_count,
        "clr_signal_count": clr_signal_count,
        "tempdb_pressure_signals": tempdb_pressure_signals,
    }

    summary = {
        "dependency_score": dependency_score,
        "dependency_level": dependency_level,
        "truncated": truncated,
    }

    return {
        "version": "4.2.0",
        "summary": summary,
        "metrics": metrics,
        "dependencies": dependencies,
        "reasons": reasons,
        "recommendations": recommendations,
        "errors": errors,
    }


def _strip_comments(sql: str) -> str:
    result: list[str] = []
    i = 0
    in_string = False
    length = len(sql)
    while i < length:
        if in_string:
            if sql[i] == "'":
                if i + 1 < length and sql[i + 1] == "'":
                    result.append("''")
                    i += 2
                    continue
                in_string = False
                result.append("'")
                i += 1
                continue
            result.append(sql[i])
            i += 1
            continue

        if sql[i : i + 2] == "--":
            while i < length and sql[i] != "\n":
                i += 1
            continue
        if sql[i : i + 2] == "/*":
            i += 2
            while i < length and sql[i : i + 2] != "*/":
                i += 1
            i = i + 2 if i < length else i
            continue
        if sql[i] == "'":
            in_string = True
            result.append("'")
            i += 1
            continue
        result.append(sql[i])
        i += 1
    return "".join(result)


def _mask_string_literals(sql: str) -> str:
    result: list[str] = []
    i = 0
    length = len(sql)
    while i < length:
        if sql[i : i + 2].lower() == "n'":
            result.append("N'__STR__'")
            i += 2
            while i < length:
                if sql[i] == "'":
                    if i + 1 < length and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        if sql[i] == "'":
            result.append("'__STR__'")
            i += 1
            while i < length:
                if sql[i] == "'":
                    if i + 1 < length and sql[i + 1] == "'":
                        i += 2
                        continue
                    i += 1
                    break
                i += 1
            continue
        result.append(sql[i])
        i += 1
    return "".join(result)


def _normalize_whitespace(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def _normalize_bracketed_identifiers(sql: str) -> str:
    without_brackets = re.sub(r"\[([^\]]+)\]", r"\1", sql)
    return re.sub(r"\s*\.\s*", ".", without_brackets)


def _normalize_identifier(value: str, case_insensitive: bool) -> str:
    return value.lower() if case_insensitive else value


def _overlaps_any(span: tuple[int, int], spans: list[tuple[int, int]]) -> bool:
    start, end = span
    for span_start, span_end in spans:
        if start < span_end and end > span_start:
            return True
    return False


def _add_linked_server(
    linked_servers: dict[str, dict[str, Any]],
    server_name: str,
    signal: str,
) -> None:
    item = linked_servers.setdefault(
        server_name,
        {"name": server_name, "signals": []},
    )
    signals = set(item["signals"])
    signals.add(signal)
    item["signals"] = sorted(signals)


def _sorted_unique(values: list[str]) -> list[str]:
    return sorted(set(values))


def _sort_cross_db(items: list[dict[str, Any]], case_insensitive: bool) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[str, str, str, str]:
        db = item["database"].lower() if case_insensitive else item["database"]
        schema = item["schema"].lower() if case_insensitive else item["schema"]
        obj = item["object"].lower() if case_insensitive else item["object"]
        return (db, schema, obj, item["kind"])

    return sorted(items, key=key)


def _sort_linked_servers(
    items: list[dict[str, Any]], case_insensitive: bool
) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> str:
        return item["name"].lower() if case_insensitive else item["name"]

    return sorted(items, key=key)


def _sort_remote_exec(items: list[dict[str, Any]], case_insensitive: bool) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]) -> tuple[str, str]:
        target = item["target"].lower() if case_insensitive else item["target"]
        return (target, item["kind"])

    return sorted(items, key=key)


def _sort_simple(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=lambda item: item["id"])


def _truncate_dependencies(
    dependencies: dict[str, list[dict[str, Any]]],
    max_items: int,
) -> tuple[dict[str, list[dict[str, Any]]], bool]:
    if max_items <= 0:
        return {key: [] for key in dependencies}, True

    total = 0
    truncated = False
    ordered_keys = [
        "cross_database",
        "linked_servers",
        "remote_exec",
        "external_access",
        "system_objects",
        "tempdb_signals",
    ]
    new_deps: dict[str, list[dict[str, Any]]] = {}
    for key in ordered_keys:
        items = dependencies.get(key, [])
        if total >= max_items:
            truncated = True
            new_deps[key] = []
            continue
        remaining = max_items - total
        if len(items) > remaining:
            new_deps[key] = items[:remaining]
            total += len(new_deps[key])
            truncated = True
            continue
        new_deps[key] = items
        total += len(items)

    return new_deps, truncated


def _score_linked_servers(linked_server_count: int) -> int:
    if linked_server_count <= 0:
        return 0
    return min(35 + (linked_server_count - 1) * 10, 55)


def _score_cross_db(cross_db_count: int) -> int:
    if cross_db_count <= 0:
        return 0
    return min(10 + max(cross_db_count - 1, 0) * 2, 20)


def _score_system_proc(system_proc_count: int) -> int:
    if system_proc_count <= 0:
        return 0
    return min(10 * min(system_proc_count, 2), 20)


def _score_tempdb(temp_table_present: bool, table_variable_present: bool) -> int:
    points = 0
    if temp_table_present:
        points += 6
    if table_variable_present:
        points += 3
    return min(points, 10)


def _score_level(score: int) -> str:
    if score >= 70:
        return "critical"
    if score >= 45:
        return "high"
    if score >= 20:
        return "medium"
    return "low"


def _reason_item(reason_id: str, weight: int) -> dict[str, Any]:
    return {
        "id": reason_id,
        "weight": weight,
        "message": REASON_MESSAGES[reason_id],
    }


def _optional_reference_metrics(sql: str, dialect: str) -> tuple[int, int]:
    if importlib.util.find_spec("app.services.tsql_analyzer") is None:  # pragma: no cover
        return 0, 0
    from app.services.tsql_analyzer import analyze_references

    try:
        result = analyze_references(sql, dialect=dialect)
    except Exception:
        return 0, 0

    references = result.get("references", {})
    tables = references.get("tables", []) if isinstance(references, dict) else []
    functions = references.get("functions", []) if isinstance(references, dict) else []
    return len(tables), len(functions)

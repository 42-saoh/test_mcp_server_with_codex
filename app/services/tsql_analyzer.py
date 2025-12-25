from __future__ import annotations

import hashlib
import logging
import re
from collections.abc import Iterable

from sqlglot import exp, parse

logger = logging.getLogger(__name__)

TABLE_PATTERN = re.compile(
    r"\b(?:FROM|JOIN|UPDATE|INTO)\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?)",
    re.IGNORECASE,
)
FUNCTION_PATTERN = re.compile(r"\b([A-Za-z_][\w]*)\s*\(", re.IGNORECASE)
FUNCTION_EXCLUDE = {
    "SELECT",
    "FROM",
    "JOIN",
    "WHERE",
    "UPDATE",
    "INTO",
    "DELETE",
    "INSERT",
    "VALUES",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "AS",
}

BEGIN_TRAN_PATTERN = re.compile(r"\bBEGIN\s+TRAN(?:SACTION)?\b", re.IGNORECASE)
COMMIT_TRAN_PATTERN = re.compile(r"\bCOMMIT(?:\s+TRAN(?:SACTION)?)?\b", re.IGNORECASE)
ROLLBACK_TRAN_PATTERN = re.compile(r"\bROLLBACK(?:\s+TRAN(?:SACTION)?)?\b", re.IGNORECASE)
SAVE_TRAN_PATTERN = re.compile(r"\bSAVE\s+TRAN(?:SACTION)?\b", re.IGNORECASE)
TRY_PATTERN = re.compile(r"\bBEGIN\s+TRY\b", re.IGNORECASE)
CATCH_PATTERN = re.compile(r"\bBEGIN\s+CATCH\b", re.IGNORECASE)
XACT_ABORT_PATTERN = re.compile(r"\bSET\s+XACT_ABORT\s+(ON|OFF)\b", re.IGNORECASE)
ISOLATION_PATTERN = re.compile(
    r"\bSET\s+TRANSACTION\s+ISOLATION\s+LEVEL\s+"
    r"(READ\s+UNCOMMITTED|READ\s+COMMITTED|REPEATABLE\s+READ|SNAPSHOT|SERIALIZABLE)\b",
    re.IGNORECASE,
)
TRANCOUNT_PATTERN = re.compile(r"@@TRANCOUNT", re.IGNORECASE)
XACT_STATE_PATTERN = re.compile(r"\bXACT_STATE\s*\(\s*\)", re.IGNORECASE)
THROW_PATTERN = re.compile(r"\bTHROW\b", re.IGNORECASE)
RAISERROR_PATTERN = re.compile(r"\bRAISERROR\b", re.IGNORECASE)

DYNAMIC_SQL_EXEC_PATTERN = re.compile(r"\bEXEC(?:UTE)?\s*\(?\s*@\w+", re.IGNORECASE)
DYNAMIC_SQL_LITERAL_PATTERN = re.compile(r"\bEXEC(?:UTE)?\s*(?:\(|\s)\s*N?'", re.IGNORECASE)
DYNAMIC_SQL_CONCAT_PATTERN = re.compile(r"\bEXEC(?:UTE)?\s*\(?\s*@\w+\s*\+", re.IGNORECASE)
SP_EXECUTESQL_PATTERN = re.compile(r"\bSP_EXECUTESQL\b", re.IGNORECASE)

DECLARE_CURSOR_PATTERN = re.compile(r"\bDECLARE\s+\w+\s+CURSOR\b", re.IGNORECASE)
OPEN_CURSOR_PATTERN = re.compile(r"\bOPEN\s+\w+\b", re.IGNORECASE)
FETCH_CURSOR_PATTERN = re.compile(r"\bFETCH\s+\w+", re.IGNORECASE)
CLOSE_CURSOR_PATTERN = re.compile(r"\bCLOSE\s+\w+\b", re.IGNORECASE)
DEALLOCATE_CURSOR_PATTERN = re.compile(r"\bDEALLOCATE\s+\w+\b", re.IGNORECASE)

OPENQUERY_PATTERN = re.compile(r"\bOPENQUERY\b", re.IGNORECASE)
OPENDATASOURCE_PATTERN = re.compile(r"\bOPENDATASOURCE\b", re.IGNORECASE)
EXEC_AT_PATTERN = re.compile(r"\bEXEC(?:UTE)?\b[^;]*\bAT\b", re.IGNORECASE)
FOUR_PART_NAME_PATTERN = re.compile(
    r"\b[A-Za-z_][\w]*\.[A-Za-z_][\w]*\.[A-Za-z_][\w]*\.[A-Za-z_][\w]*\b",
    re.IGNORECASE,
)

XP_PROC_PATTERN = re.compile(r"\bxp_\w+\b", re.IGNORECASE)
SP_OA_PATTERN = re.compile(r"\bsp_OA\w+\b", re.IGNORECASE)
SP_CONFIGURE_PATTERN = re.compile(r"\bsp_configure\b", re.IGNORECASE)

TEMP_TABLE_PATTERN = re.compile(r"##?[A-Za-z_][\w]*", re.IGNORECASE)
TEMP_TABLE_CREATE_PATTERN = re.compile(r"\bCREATE\s+TABLE\s+##?[A-Za-z_][\w]*\b", re.IGNORECASE)
TEMP_TABLE_INSERT_PATTERN = re.compile(r"\bINSERT\s+INTO\s+##?[A-Za-z_][\w]*\b", re.IGNORECASE)
TEMP_TABLE_DROP_PATTERN = re.compile(r"\bDROP\s+TABLE\s+##?[A-Za-z_][\w]*\b", re.IGNORECASE)

TABLE_VARIABLE_PATTERN = re.compile(r"\bDECLARE\s+@\w+\s+TABLE\b", re.IGNORECASE)
MERGE_PATTERN = re.compile(r"\bMERGE\b", re.IGNORECASE)
OUTPUT_CLAUSE_PATTERN = re.compile(r"\bOUTPUT\b\s+(?:INSERTED|DELETED)\b", re.IGNORECASE)
SCOPE_IDENTITY_PATTERN = re.compile(r"\bSCOPE_IDENTITY\s*\(\s*\)", re.IGNORECASE)
AT_AT_IDENTITY_PATTERN = re.compile(r"@@IDENTITY\b", re.IGNORECASE)
IDENT_CURRENT_PATTERN = re.compile(r"\bIDENT_CURRENT\s*\(", re.IGNORECASE)
OUTPUT_PATTERN = re.compile(r"\bOUTPUT\b", re.IGNORECASE)
INSERTED_PATTERN = re.compile(r"\bINSERTED\b", re.IGNORECASE)
DELETED_PATTERN = re.compile(r"\bDELETED\b", re.IGNORECASE)

GETDATE_PATTERN = re.compile(r"\bGETDATE\s*\(\s*\)", re.IGNORECASE)
SYSDATETIME_PATTERN = re.compile(r"\bSYSDATETIME\s*\(\s*\)", re.IGNORECASE)
NEWID_PATTERN = re.compile(r"\bNEWID\s*\(\s*\)", re.IGNORECASE)
RAND_PATTERN = re.compile(r"\bRAND\s*\(\s*\)", re.IGNORECASE)
AT_AT_ERROR_PATTERN = re.compile(r"@@ERROR\b", re.IGNORECASE)

CONTROL_FLOW_TOKEN_PATTERN = re.compile(
    r"(?P<begin_try>\bBEGIN\s+TRY\b)|"
    r"(?P<begin_catch>\bBEGIN\s+CATCH\b)|"
    r"(?P<if>\bIF\b)|"
    r"(?P<while>\bWHILE\b)|"
    r"(?P<return>\bRETURN\b)|"
    r"(?P<goto>\bGOTO\b)",
    re.IGNORECASE,
)
CONTROL_FLOW_LABEL_PATTERN = re.compile(
    r"^[ \t]*[A-Za-z_][\w]*\s*:\s*(?:--.*)?$",
    re.IGNORECASE | re.MULTILINE,
)
CONTROL_FLOW_NESTING_PATTERN = re.compile(
    r"(?P<begin_try>\bBEGIN\s+TRY\b)|"
    r"(?P<begin_catch>\bBEGIN\s+CATCH\b)|"
    r"(?P<end_try>\bEND\s+TRY\b)|"
    r"(?P<end_catch>\bEND\s+CATCH\b)|"
    r"(?P<begin>\bBEGIN\b)|"
    r"(?P<end>\bEND\b)|"
    r"(?P<if>\bIF\b)|"
    r"(?P<while>\bWHILE\b)",
    re.IGNORECASE,
)

CONTROL_FLOW_NODE_LIMIT = 200
CONTROL_FLOW_EDGE_LIMIT = 400

TABLE_NAME_PATTERN = re.compile(
    r"(?P<table>(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)"
    r"(?:\s*\.\s*(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)){0,2})",
    re.IGNORECASE,
)
INSERT_PATTERN = re.compile(rf"\bINSERT\s+INTO\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE)
UPDATE_PATTERN = re.compile(rf"\bUPDATE\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE)
DELETE_PATTERN = re.compile(rf"\bDELETE\s+FROM\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE)
DELETE_ALIAS_PATTERN = re.compile(
    rf"\bDELETE\s+\w+\s+FROM\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE
)
MERGE_PATTERN_REGEX = re.compile(rf"\bMERGE\s+INTO\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE)
TRUNCATE_PATTERN = re.compile(rf"\bTRUNCATE\s+TABLE\s+{TABLE_NAME_PATTERN.pattern}", re.IGNORECASE)
SELECT_INTO_PATTERN = re.compile(
    rf"\bSELECT\b[\s\S]*?\bINTO\s+{TABLE_NAME_PATTERN.pattern}",
    re.IGNORECASE,
)


def analyze_references(sql: str, dialect: str = "tsql") -> dict[str, object]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("analyze_references: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    references = {"tables": [], "functions": []}
    errors: list[str] = []

    try:
        expressions = parse(sql, read=dialect)
        parsed_tables = _sorted_unique(_extract_tables(expressions))
        parsed_functions = _sorted_unique(_extract_functions(expressions))
        fallback = _fallback_references(sql)
        references["tables"] = _sorted_unique(parsed_tables + fallback["tables"])
        references["functions"] = _sorted_unique(parsed_functions + fallback["functions"])
    except Exception as exc:  # pragma: no cover - narrow to parse failure
        errors.append(f"parse_error: {exc}")
        references = _fallback_references(sql)

    return {"references": references, "errors": errors}


def analyze_transactions(sql: str) -> dict[str, object]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("analyze_transactions: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    begin_count = len(BEGIN_TRAN_PATTERN.findall(sql))
    commit_count = len(COMMIT_TRAN_PATTERN.findall(sql))
    rollback_count = len(ROLLBACK_TRAN_PATTERN.findall(sql))
    savepoint_count = len(SAVE_TRAN_PATTERN.findall(sql))
    has_try = bool(TRY_PATTERN.search(sql))
    has_catch = bool(CATCH_PATTERN.search(sql))
    has_try_catch = has_try and has_catch

    xact_abort = None
    for match in XACT_ABORT_PATTERN.finditer(sql):
        xact_abort = match.group(1).upper()

    isolation_level = None
    for match in ISOLATION_PATTERN.finditer(sql):
        isolation_level = " ".join(match.group(1).upper().split())

    signals: list[str] = []
    seen = set()

    def add_signal(signal: str) -> None:
        if signal in seen or len(seen) >= 10:
            return
        seen.add(signal)
        signals.append(signal)

    if begin_count:
        add_signal("BEGIN TRAN")
    if commit_count:
        add_signal("COMMIT")
    if rollback_count:
        add_signal("ROLLBACK")
    if savepoint_count:
        add_signal("SAVE TRAN")
    if has_try_catch:
        add_signal("TRY/CATCH")
    if xact_abort:
        add_signal(f"XACT_ABORT {xact_abort}")
    if isolation_level:
        add_signal(f"ISOLATION LEVEL {isolation_level}")
    if TRANCOUNT_PATTERN.search(sql):
        add_signal("@@TRANCOUNT")
    if XACT_STATE_PATTERN.search(sql):
        add_signal("XACT_STATE()")
    if THROW_PATTERN.search(sql):
        add_signal("THROW")
    if RAISERROR_PATTERN.search(sql):
        add_signal("RAISERROR")

    uses_transaction = any([begin_count, commit_count, rollback_count, savepoint_count])

    return {
        "uses_transaction": uses_transaction,
        "begin_count": begin_count,
        "commit_count": commit_count,
        "rollback_count": rollback_count,
        "savepoint_count": savepoint_count,
        "has_try_catch": has_try_catch,
        "xact_abort": xact_abort,
        "isolation_level": isolation_level,
        "signals": signals,
    }


def analyze_migration_impacts(sql: str) -> dict[str, object]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("analyze_migration_impacts: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    normalized = re.sub(r"\s+", " ", sql).strip()
    items: dict[str, dict[str, object]] = {}
    signal_sets: dict[str, set[str]] = {}

    def ensure_item(
        item_id: str,
        category: str,
        severity: str,
        title: str,
        details: str,
    ) -> None:
        if item_id in items:
            return
        items[item_id] = {
            "id": item_id,
            "category": category,
            "severity": severity,
            "title": title,
            "signals": [],
            "details": details,
        }
        signal_sets[item_id] = set()

    def add_signal(item_id: str, signal: str) -> None:
        signals = items[item_id]["signals"]
        signal_set = signal_sets[item_id]
        if signal in signal_set or len(signal_set) >= 10:
            return
        signal_set.add(signal)
        signals.append(signal)

    def add_item_with_signals(
        item_id: str,
        category: str,
        severity: str,
        title: str,
        details: str,
        signals: list[str],
    ) -> None:
        ensure_item(item_id, category, severity, title, details)
        for signal in signals:
            add_signal(item_id, signal)

    dynamic_signals: list[str] = []
    if SP_EXECUTESQL_PATTERN.search(normalized):
        dynamic_signals.append("sp_executesql")
    if DYNAMIC_SQL_EXEC_PATTERN.search(normalized):
        dynamic_signals.append("EXEC(@var)")
    if DYNAMIC_SQL_LITERAL_PATTERN.search(normalized):
        dynamic_signals.append("EXEC('...')")
    if DYNAMIC_SQL_CONCAT_PATTERN.search(normalized):
        dynamic_signals.append("EXEC + concat")
    if dynamic_signals:
        add_item_with_signals(
            "IMP_DYN_SQL",
            "dynamic_sql",
            "high",
            "Dynamic SQL detected",
            "Dynamic SQL often requires refactoring to safe parameterization in Java/MyBatis.",
            dynamic_signals,
        )

    cursor_signals: list[str] = []
    if DECLARE_CURSOR_PATTERN.search(normalized):
        cursor_signals.append("DECLARE CURSOR")
    if OPEN_CURSOR_PATTERN.search(normalized):
        cursor_signals.append("OPEN CURSOR")
    if FETCH_CURSOR_PATTERN.search(normalized):
        cursor_signals.append("FETCH CURSOR")
    if CLOSE_CURSOR_PATTERN.search(normalized):
        cursor_signals.append("CLOSE CURSOR")
    if DEALLOCATE_CURSOR_PATTERN.search(normalized):
        cursor_signals.append("DEALLOCATE CURSOR")
    if cursor_signals:
        add_item_with_signals(
            "IMP_CURSOR",
            "cursor",
            "high",
            "Cursor usage detected",
            "Cursors often require set-based rewrites when moving to Java/MyBatis.",
            cursor_signals,
        )

    linked_signals: list[str] = []
    if OPENQUERY_PATTERN.search(normalized):
        linked_signals.append("OPENQUERY")
    if OPENDATASOURCE_PATTERN.search(normalized):
        linked_signals.append("OPENDATASOURCE")
    if EXEC_AT_PATTERN.search(normalized):
        linked_signals.append("EXEC AT")
    if FOUR_PART_NAME_PATTERN.search(normalized):
        linked_signals.append("FOUR_PART_NAME")
    if linked_signals:
        add_item_with_signals(
            "IMP_LINKED_SERVER",
            "linked_server",
            "high",
            "Linked server usage detected",
            "Linked server or remote execution patterns may need redesign in Java/MyBatis.",
            linked_signals,
        )

    system_proc_signals: list[str] = []
    if XP_PROC_PATTERN.search(normalized):
        system_proc_signals.append("xp_")
    if SP_OA_PATTERN.search(normalized):
        system_proc_signals.append("sp_OA*")
    if SP_CONFIGURE_PATTERN.search(normalized):
        system_proc_signals.append("sp_configure")
    if system_proc_signals:
        add_item_with_signals(
            "IMP_SYSTEM_PROC",
            "system_proc",
            "high",
            "System procedure usage detected",
            "System-level procedures may not map directly to Java/MyBatis and require review.",
            system_proc_signals,
        )

    temp_table_signals: list[str] = []
    if TEMP_TABLE_PATTERN.search(normalized):
        temp_table_signals.append("TEMP_TABLE")
    if TEMP_TABLE_CREATE_PATTERN.search(normalized):
        temp_table_signals.append("CREATE TABLE #")
    if TEMP_TABLE_INSERT_PATTERN.search(normalized):
        temp_table_signals.append("INSERT INTO #")
    if TEMP_TABLE_DROP_PATTERN.search(normalized):
        temp_table_signals.append("DROP TABLE #")
    if temp_table_signals:
        add_item_with_signals(
            "IMP_TEMP_TABLE",
            "temp_table",
            "medium",
            "Temporary table usage detected",
            "Temporary tables may need alternative structures in Java/MyBatis workflows.",
            temp_table_signals,
        )

    if TABLE_VARIABLE_PATTERN.search(normalized):
        add_item_with_signals(
            "IMP_TABLE_VARIABLE",
            "table_variable",
            "medium",
            "Table variable usage detected",
            "Table variables may need to be replaced with typed collections in Java/MyBatis.",
            ["DECLARE @table"],
        )

    if MERGE_PATTERN.search(normalized):
        add_item_with_signals(
            "IMP_MERGE",
            "merge",
            "medium",
            "MERGE statement detected",
            "MERGE statements can require careful translation to Java/MyBatis logic.",
            ["MERGE"],
        )

    if OUTPUT_CLAUSE_PATTERN.search(normalized):
        add_item_with_signals(
            "IMP_OUTPUT_CLAUSE",
            "output_clause",
            "medium",
            "OUTPUT clause detected",
            "OUTPUT clauses may need manual handling in Java/MyBatis result flows.",
            ["OUTPUT"],
        )

    identity_signals: list[str] = []
    if SCOPE_IDENTITY_PATTERN.search(normalized):
        identity_signals.append("SCOPE_IDENTITY()")
    if AT_AT_IDENTITY_PATTERN.search(normalized):
        identity_signals.append("@@IDENTITY")
    if IDENT_CURRENT_PATTERN.search(normalized):
        identity_signals.append("IDENT_CURRENT")
    if identity_signals:
        add_item_with_signals(
            "IMP_IDENTITY",
            "identity",
            "medium",
            "Identity retrieval detected",
            "Identity retrieval functions may need explicit key handling in Java/MyBatis.",
            identity_signals,
        )

    nondeterminism_signals: list[str] = []
    if GETDATE_PATTERN.search(normalized):
        nondeterminism_signals.append("GETDATE()")
    if SYSDATETIME_PATTERN.search(normalized):
        nondeterminism_signals.append("SYSDATETIME()")
    if NEWID_PATTERN.search(normalized):
        nondeterminism_signals.append("NEWID()")
    if RAND_PATTERN.search(normalized):
        nondeterminism_signals.append("RAND()")
    if nondeterminism_signals:
        add_item_with_signals(
            "IMP_NONDETERMINISM",
            "nondeterminism",
            "low",
            "Non-deterministic function usage detected",
            "Non-deterministic functions may impact repeatability in migrations.",
            nondeterminism_signals,
        )

    error_signals: list[str] = []
    if RAISERROR_PATTERN.search(normalized):
        error_signals.append("RAISERROR")
    if THROW_PATTERN.search(normalized):
        error_signals.append("THROW")
    if AT_AT_ERROR_PATTERN.search(normalized):
        error_signals.append("@@ERROR")
    if error_signals:
        add_item_with_signals(
            "IMP_ERROR_SIGNALING",
            "error_signaling",
            "low",
            "Error signaling detected",
            "Error signaling patterns may need aligned exception handling in Java.",
            error_signals,
        )

    has_impact = bool(items)
    return {
        "has_impact": has_impact,
        "items": list(items.values()),
    }


def analyze_control_flow(sql: str, dialect: str = "tsql") -> dict[str, object]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("analyze_control_flow: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    errors: list[str] = []
    ast_counts = {"if": 0, "try": 0, "return": 0}
    try:
        expressions = parse(sql, read=dialect)
        ast_counts["if"] = sum(1 for expression in expressions for _ in expression.find_all(exp.If))
        ast_counts["try"] = sum(
            1 for expression in expressions for _ in expression.find_all(exp.Try)
        )
        ast_counts["return"] = sum(
            1 for expression in expressions for _ in expression.find_all(exp.Return)
        )
    except Exception as exc:  # pragma: no cover - fallback for parse failure
        errors.append(f"parse_error: {exc}")

    tokens = _scan_control_flow_tokens(sql)
    label_count = len(CONTROL_FLOW_LABEL_PATTERN.findall(sql))

    counts = {
        "if": max(ast_counts["if"], sum(1 for token in tokens if token == "if")),
        "while": sum(1 for token in tokens if token == "while"),
        "try": max(ast_counts["try"], sum(1 for token in tokens if token == "try")),
        "catch": sum(1 for token in tokens if token == "catch"),
        "return": max(ast_counts["return"], sum(1 for token in tokens if token == "return")),
        "goto": sum(1 for token in tokens if token == "goto"),
    }

    signals = _control_flow_signals(tokens, label_count)
    max_nesting_depth = _estimate_nesting_depth(sql)

    has_try_catch = bool(counts["try"] or counts["catch"])
    branch_count = counts["if"]
    loop_count = counts["while"]
    return_count = counts["return"]
    goto_count = counts["goto"]

    cyclomatic_complexity = (
        1 + branch_count + loop_count + (1 if has_try_catch else 0) + (1 if goto_count > 0 else 0)
    )

    graph, graph_errors = _build_control_flow_graph(tokens)
    errors.extend(graph_errors)

    summary = {
        "has_branching": branch_count > 0,
        "has_loops": loop_count > 0,
        "has_try_catch": has_try_catch,
        "has_goto": goto_count > 0,
        "has_return": return_count > 0,
        "branch_count": branch_count,
        "loop_count": loop_count,
        "return_count": return_count,
        "goto_count": goto_count,
        "max_nesting_depth": max_nesting_depth,
        "cyclomatic_complexity": cyclomatic_complexity,
    }

    return {
        "control_flow": {
            "summary": summary,
            "graph": graph,
            "signals": signals,
        },
        "errors": errors,
    }


def analyze_data_changes(sql: str, dialect: str = "tsql") -> dict[str, object]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    logger.info("analyze_data_changes: sql_len=%s sql_hash=%s", len(sql), sql_hash)

    operations = {
        "insert": {"count": 0, "tables": []},
        "update": {"count": 0, "tables": []},
        "delete": {"count": 0, "tables": []},
        "merge": {"count": 0, "tables": []},
        "truncate": {"count": 0, "tables": []},
        "select_into": {"count": 0, "tables": []},
    }
    op_tables = {key: set() for key in operations}
    notes: list[str] = []
    errors: list[str] = []
    unknown_ops: set[str] = set()

    def add_operation(op: str, table: str | None) -> None:
        operations[op]["count"] += 1
        if table:
            op_tables[op].add(table)
        else:
            unknown_ops.add(op)

    parse_failed = False
    try:
        expressions = parse(sql, read=dialect)
        for expression in expressions:
            for node in expression.find_all(exp.Insert):
                add_operation("insert", _table_name_from_expression(node.this))
            for node in expression.find_all(exp.Update):
                if node.find_ancestor(exp.Merge):
                    continue
                add_operation("update", _table_name_from_expression(node.this))
            for node in expression.find_all(exp.Delete):
                add_operation("delete", _table_name_from_expression(node.this))
            for node in expression.find_all(exp.Merge):
                add_operation("merge", _table_name_from_expression(node.this))
            for node in expression.find_all(exp.Select):
                into_expr = node.args.get("into")
                if into_expr is not None:
                    target = None
                    if hasattr(into_expr, "this"):
                        target = _table_name_from_expression(into_expr.this)
                    if target is None:
                        target = _table_name_from_expression(into_expr)
                    add_operation("select_into", target)
    except Exception as exc:  # pragma: no cover - parse failure fallback
        errors.append(f"parse_error: {exc}")
        parse_failed = True

    fallback_ops = _fallback_data_changes(sql)
    for op, payload in fallback_ops["operations"].items():
        if parse_failed or operations[op]["count"] == 0:
            operations[op]["count"] = payload["count"]
            op_tables[op] = set(payload["tables"])
            if payload["unknown"]:
                unknown_ops.add(op)

    for op, tables in op_tables.items():
        operations[op]["tables"] = sorted(tables)
        if operations[op]["count"] > 0 and not tables and op in unknown_ops:
            notes.append(f"{op.upper()} detected but target table uncertain.")

    table_operations_map: dict[str, set[str]] = {}
    for op, tables in op_tables.items():
        for table in tables:
            table_operations_map.setdefault(table, set()).add(op)

    table_operations = [
        {"table": table, "ops": sorted(ops)} for table, ops in sorted(table_operations_map.items())
    ]

    signals = _data_change_signals(operations, sql)
    has_writes = any(
        operations[key]["count"] > 0
        for key in ["insert", "update", "delete", "merge", "truncate", "select_into"]
    )

    return {
        "data_changes": {
            "has_writes": has_writes,
            "operations": operations,
            "table_operations": table_operations,
            "signals": signals,
            "notes": notes,
        },
        "errors": errors,
    }


def _fallback_references(sql: str) -> dict[str, list[str]]:
    tables = [match.group(1) for match in TABLE_PATTERN.finditer(sql)]
    functions = []
    for match in FUNCTION_PATTERN.finditer(sql):
        name = match.group(1).upper()
        if name in FUNCTION_EXCLUDE:
            continue
        functions.append(name)
    return {
        "tables": _sorted_unique(tables),
        "functions": _sorted_unique(functions),
    }


def _extract_tables(expressions: Iterable[exp.Expression]) -> list[str]:
    tables: list[str] = []
    for expression in expressions:
        for table in expression.find_all(exp.Table):
            if table.find_ancestor(exp.Create):
                continue

            parts = [part for part in (table.catalog, table.db, table.name) if part]
            if parts:
                tables.append(".".join(parts).upper())
    return tables


def _extract_functions(expressions: Iterable[exp.Expression]) -> list[str]:
    functions: list[str] = []
    for expression in expressions:
        for func in expression.find_all((exp.Anonymous, exp.Func, exp.UserDefinedFunction)):
            name = _function_name(func)
            if name:
                functions.append(name.upper())
    return functions


def _function_name(node: exp.Expression) -> str | None:
    name: str | None
    if isinstance(node, exp.Anonymous):
        name = node.name
    elif isinstance(node, exp.UserDefinedFunction):
        name = node.name
    elif isinstance(node, exp.Func):
        name = node.sql_name()
    else:
        return None

    if not name:
        return None

    return name.split(".")[-1]


def _sorted_unique(values: Iterable[str]) -> list[str]:
    normalized = {value.upper() for value in values if value}
    return sorted(normalized)


def _strip_sql_comments(sql: str) -> str:
    no_block = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", no_block)


def _normalize_identifier(identifier: str) -> str | None:
    cleaned = identifier.strip()
    if not cleaned:
        return None
    if cleaned.startswith("[") and cleaned.endswith("]"):
        cleaned = cleaned[1:-1]
    if cleaned.startswith('"') and cleaned.endswith('"'):
        cleaned = cleaned[1:-1]
    return cleaned or None


def _normalize_table_name(raw: str) -> str | None:
    if not raw:
        return None
    raw = raw.strip().strip(";")
    raw = raw.strip("()")
    parts = []
    for part in re.split(r"\s*\.\s*", raw):
        normalized = _normalize_identifier(part)
        if normalized:
            parts.append(normalized)
    if not parts:
        return None
    return ".".join(parts).upper()


def _table_name_from_expression(node: exp.Expression | None) -> str | None:
    if node is None:
        return None
    if isinstance(node, exp.Table):
        parts = [part for part in (node.catalog, node.db, node.name) if part]
        if parts:
            return _normalize_table_name(".".join(parts))
    if isinstance(node, exp.Identifier):
        return _normalize_table_name(node.name or "")
    if isinstance(node, exp.Expression) and hasattr(node, "name"):
        name = getattr(node, "name", None)
        if isinstance(name, str):
            return _normalize_table_name(name)
    if hasattr(node, "this") and isinstance(node.this, str):
        return _normalize_table_name(node.this)
    return None


def _fallback_data_changes(sql: str) -> dict[str, object]:
    stripped = _strip_sql_comments(sql)
    operations = {
        "insert": {"count": 0, "tables": [], "unknown": False},
        "update": {"count": 0, "tables": [], "unknown": False},
        "delete": {"count": 0, "tables": [], "unknown": False},
        "merge": {"count": 0, "tables": [], "unknown": False},
        "truncate": {"count": 0, "tables": [], "unknown": False},
        "select_into": {"count": 0, "tables": [], "unknown": False},
    }

    def add_match(op: str, table: str | None) -> None:
        operations[op]["count"] += 1
        if table:
            operations[op]["tables"].append(table)
        else:
            operations[op]["unknown"] = True

    def is_merge_context(start: int) -> bool:
        statement_start = stripped.rfind(";", 0, start)
        if statement_start == -1:
            statement_start = 0
        context = stripped[statement_start:start]
        return bool(MERGE_PATTERN.search(context))

    for match in INSERT_PATTERN.finditer(stripped):
        add_match("insert", _normalize_table_name(match.group("table")))
    for match in UPDATE_PATTERN.finditer(stripped):
        if is_merge_context(match.start()):
            continue
        add_match("update", _normalize_table_name(match.group("table")))
    for match in DELETE_PATTERN.finditer(stripped):
        if is_merge_context(match.start()):
            continue
        add_match("delete", _normalize_table_name(match.group("table")))
    for match in DELETE_ALIAS_PATTERN.finditer(stripped):
        if is_merge_context(match.start()):
            continue
        add_match("delete", _normalize_table_name(match.group("table")))
    for match in MERGE_PATTERN_REGEX.finditer(stripped):
        add_match("merge", _normalize_table_name(match.group("table")))
    for match in TRUNCATE_PATTERN.finditer(stripped):
        add_match("truncate", _normalize_table_name(match.group("table")))
    for match in SELECT_INTO_PATTERN.finditer(stripped):
        add_match("select_into", _normalize_table_name(match.group("table")))

    for op in operations.values():
        op["tables"] = _sorted_unique(op["tables"])
    return {"operations": operations}


def _data_change_signals(operations: dict[str, dict[str, object]], sql: str) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()

    def add_signal(signal: str) -> None:
        if signal in seen or len(seen) >= 15:
            return
        seen.add(signal)
        signals.append(signal)

    if operations["insert"]["count"]:
        add_signal("INSERT")
    if operations["update"]["count"]:
        add_signal("UPDATE")
    if operations["delete"]["count"]:
        add_signal("DELETE")
    if operations["merge"]["count"]:
        add_signal("MERGE")
    if operations["truncate"]["count"]:
        add_signal("TRUNCATE")
    if operations["select_into"]["count"]:
        add_signal("SELECT INTO")

    stripped = _strip_sql_comments(sql)
    if OUTPUT_PATTERN.search(stripped):
        add_signal("OUTPUT")
    if INSERTED_PATTERN.search(stripped):
        add_signal("INSERTED")
    if DELETED_PATTERN.search(stripped):
        add_signal("DELETED")

    return signals


def _scan_control_flow_tokens(sql: str) -> list[str]:
    tokens: list[str] = []
    for match in CONTROL_FLOW_TOKEN_PATTERN.finditer(sql):
        kind = match.lastgroup
        if not kind:
            continue
        if kind == "begin_try":
            tokens.append("try")
        elif kind == "begin_catch":
            tokens.append("catch")
        elif kind == "if":
            tokens.append("if")
        elif kind == "while":
            tokens.append("while")
        elif kind == "return":
            tokens.append("return")
        elif kind == "goto":
            tokens.append("goto")
    return tokens


def _control_flow_signals(tokens: list[str], label_count: int) -> list[str]:
    signals: list[str] = []
    seen: set[str] = set()

    def add_signal(signal: str) -> None:
        if signal in seen or len(seen) >= 10:
            return
        seen.add(signal)
        signals.append(signal)

    for token in tokens:
        if token == "if":
            add_signal("IF")
        elif token == "while":
            add_signal("WHILE")
        elif token in {"try", "catch"}:
            add_signal("TRY/CATCH")
        elif token == "return":
            add_signal("RETURN")
        elif token == "goto":
            add_signal("GOTO")

    if label_count:
        add_signal("LABEL")

    return signals


def _estimate_nesting_depth(sql: str) -> int:
    depth = 0
    max_depth = 0
    for match in CONTROL_FLOW_NESTING_PATTERN.finditer(sql):
        kind = match.lastgroup
        if kind in {"begin_try", "begin_catch", "begin", "if", "while"}:
            depth += 1
            max_depth = max(max_depth, depth)
        elif kind in {"end_try", "end_catch", "end"}:
            depth = max(0, depth - 1)
    return max_depth


def _build_control_flow_graph(tokens: list[str]) -> tuple[dict[str, object], list[str]]:
    errors: list[str] = []
    nodes: list[dict[str, str]] = [{"id": "n0", "type": "start", "label": "START"}]

    node_types: list[dict[str, str]] = []
    for token in tokens:
        if token == "if":
            node_types.append({"type": "if", "label": "IF"})
        elif token == "while":
            node_types.append({"type": "while", "label": "WHILE"})
        elif token == "try":
            node_types.append({"type": "try", "label": "TRY"})
        elif token == "catch":
            node_types.append({"type": "catch", "label": "CATCH"})
        elif token == "return":
            node_types.append({"type": "return", "label": "RETURN"})
        elif token == "goto":
            node_types.append({"type": "goto", "label": "GOTO"})

    for index, node in enumerate(node_types, start=1):
        nodes.append({"id": f"n{index}", **node})

    end_id = f"n{len(nodes)}"
    nodes.append({"id": end_id, "type": "end", "label": "END"})

    if len(nodes) > CONTROL_FLOW_NODE_LIMIT:
        errors.append("control_flow_graph_truncated: node_limit_exceeded")
        nodes = nodes[: CONTROL_FLOW_NODE_LIMIT - 1]
        end_id = f"n{len(nodes)}"
        nodes.append({"id": end_id, "type": "end", "label": "END"})

    edges: list[dict[str, str]] = []
    for index in range(len(nodes) - 1):
        current = nodes[index]
        next_node = nodes[index + 1]
        current_type = current["type"]
        if current_type == "if":
            edges.append({"from": current["id"], "to": next_node["id"], "label": "true"})
            edges.append({"from": current["id"], "to": next_node["id"], "label": "false"})
        elif current_type == "while":
            edges.append({"from": current["id"], "to": current["id"], "label": "loop"})
            edges.append({"from": current["id"], "to": next_node["id"], "label": "exit"})
        elif current_type == "try":
            if next_node["type"] == "catch":
                edges.append({"from": current["id"], "to": next_node["id"], "label": "on_error"})
                follow = nodes[index + 2] if index + 2 < len(nodes) else None
                if follow:
                    edges.append({"from": current["id"], "to": follow["id"], "label": "next"})
            else:
                edges.append({"from": current["id"], "to": next_node["id"], "label": "next"})
        elif current_type == "return":
            edges.append({"from": current["id"], "to": end_id, "label": "return"})
        elif current_type == "goto":
            edges.append({"from": current["id"], "to": end_id, "label": "goto"})
        else:
            edges.append({"from": current["id"], "to": next_node["id"], "label": "next"})

    if len(edges) > CONTROL_FLOW_EDGE_LIMIT:
        errors.append("control_flow_graph_truncated: edge_limit_exceeded")
        edges = edges[:CONTROL_FLOW_EDGE_LIMIT]

    graph = {"nodes": nodes, "edges": edges}
    return graph, errors

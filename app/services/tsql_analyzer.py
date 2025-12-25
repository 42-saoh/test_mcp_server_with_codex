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

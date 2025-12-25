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

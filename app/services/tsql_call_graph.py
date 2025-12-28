from __future__ import annotations

import importlib.util
import logging
import re
from dataclasses import dataclass

from app.services.safe_sql import strip_comments_and_strings, summarize_sql

logger = logging.getLogger(__name__)

SIGNAL_LIMIT = 10

IDENTIFIER_PATTERN = r"(?:\[[^\]]+\]|[A-Za-z_][\w$#]*)"
QUALIFIED_NAME_PATTERN = rf"{IDENTIFIER_PATTERN}(?:\s*\.\s*{IDENTIFIER_PATTERN})*"


@dataclass(frozen=True)
class SqlObject:
    name: str
    type: str
    sql: str


@dataclass(frozen=True)
class Options:
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_functions: bool = True
    include_procedures: bool = True
    ignore_dynamic_exec: bool = True
    max_nodes: int = 500
    max_edges: int = 2000


def build_call_graph(objects: list[SqlObject], options: Options) -> dict[str, object]:
    errors: list[dict[str, str]] = []
    logger.info(
        "build_call_graph: objects=%s include_functions=%s include_procedures=%s",
        len(objects),
        options.include_functions,
        options.include_procedures,
    )

    filtered_objects = [obj for obj in objects if _include_object(obj, options)]

    node_entries: list[dict[str, str]] = []
    node_by_id: dict[str, dict[str, str]] = {}
    base_name_index: dict[str, list[str]] = {}

    for obj in filtered_objects:
        normalized_id = _normalize_full_name(obj.name, case_insensitive=options.case_insensitive)
        if not normalized_id:
            continue
        if normalized_id in node_by_id:
            continue
        node = {
            "id": normalized_id,
            "name": obj.name,
            "type": obj.type,
        }
        node_by_id[normalized_id] = node
        node_entries.append(node)
        _index_base_name(normalized_id, base_name_index)

    exec_pattern, function_pattern, function_definition_pattern = _build_patterns(
        options.case_insensitive
    )

    edge_stats: dict[tuple[str, str, str], dict[str, object]] = {}
    ambiguous_calls: set[tuple[str, str]] = set()

    for obj in filtered_objects:
        caller_id = _normalize_full_name(obj.name, case_insensitive=options.case_insensitive)
        if caller_id not in node_by_id:
            continue

        summary = summarize_sql(obj.sql)
        logger.info(
            "build_call_graph: object=%s sql_len=%s sql_hash=%s",
            obj.name,
            summary["len"],
            summary["sha256_8"],
        )

        cleaned_sql = _normalize_whitespace(strip_comments_and_strings(obj.sql))

        for match in exec_pattern.finditer(cleaned_sql):
            name = match.group("name")
            if options.ignore_dynamic_exec and _is_dynamic_exec(name, options):
                continue
            kind = match.group("kind").lower()
            signal = "EXECUTE" if kind == "execute" else "EXEC"
            resolved = _resolve_target(
                name,
                base_name_index,
                node_by_id,
                options,
                object_type="procedure",
                ambiguous_calls=ambiguous_calls,
                caller_name=obj.name,
                errors=errors,
            )
            if resolved:
                _record_edge(edge_stats, caller_id, resolved, kind, signal)

        definition_spans = _find_definition_spans(cleaned_sql, function_definition_pattern)
        for match in function_pattern.finditer(cleaned_sql):
            if match.span("name") in definition_spans:
                continue
            name = match.group("name")
            resolved = _resolve_target(
                name,
                base_name_index,
                node_by_id,
                options,
                object_type="function",
                ambiguous_calls=ambiguous_calls,
                caller_name=obj.name,
                errors=errors,
            )
            if resolved:
                _record_edge(edge_stats, caller_id, resolved, "function_call", "FUNCTION")

    node_entries.sort(key=lambda item: item["id"])

    truncated = False
    if len(node_entries) > options.max_nodes:
        node_entries = node_entries[: options.max_nodes]
        node_by_id = {node["id"]: node for node in node_entries}
        truncated = True
        errors.append(
            {
                "id": "NODE_LIMIT_EXCEEDED",
                "message": f"Node limit exceeded. max_nodes={options.max_nodes}.",
            }
        )

    edges = _build_edges(edge_stats, node_by_id)
    edges.sort(key=lambda item: (item["from"], item["to"], item["kind"]))

    if len(edges) > options.max_edges:
        edges = edges[: options.max_edges]
        truncated = True
        errors.append(
            {
                "id": "EDGE_LIMIT_EXCEEDED",
                "message": f"Edge limit exceeded. max_edges={options.max_edges}.",
            }
        )

    topology = _build_topology(node_entries, edges)
    has_cycles, cycle_error = _detect_cycles(edges)
    if cycle_error:
        errors.append(cycle_error)

    return {
        "version": "2.4.0",
        "summary": {
            "object_count": len(objects),
            "node_count": len(node_entries),
            "edge_count": len(edges),
            "has_cycles": has_cycles,
            "truncated": truncated,
        },
        "graph": {
            "nodes": node_entries,
            "edges": edges,
        },
        "topology": topology,
        "errors": errors,
    }


def _include_object(obj: SqlObject, options: Options) -> bool:
    obj_type = obj.type.lower()
    if obj_type == "procedure":
        return options.include_procedures
    if obj_type == "function":
        return options.include_functions
    return options.include_procedures or options.include_functions


def _index_base_name(full_id: str, base_name_index: dict[str, list[str]]) -> None:
    base_name = _split_identifier(full_id, case_insensitive=False)[1]
    base_name_index.setdefault(base_name, []).append(full_id)


def _build_patterns(
    case_insensitive: bool,
) -> tuple[re.Pattern[str], re.Pattern[str], re.Pattern[str]]:
    flags = re.IGNORECASE if case_insensitive else 0
    exec_pattern = re.compile(
        rf"\b(?P<kind>EXEC(?:UTE)?)\s+(?!\s*@)(?!\s*\()(?P<name>{QUALIFIED_NAME_PATTERN})",
        flags,
    )
    function_pattern = re.compile(rf"\b(?P<name>{QUALIFIED_NAME_PATTERN})\s*\(", flags)
    function_definition_pattern = re.compile(
        rf"\b(?:CREATE|ALTER)\s+FUNCTION\s+(?P<name>{QUALIFIED_NAME_PATTERN})\s*\(",
        flags,
    )
    return exec_pattern, function_pattern, function_definition_pattern


def _normalize_whitespace(sql: str) -> str:
    return " ".join(sql.split())


def _find_definition_spans(
    sql: str, function_definition_pattern: re.Pattern[str]
) -> set[tuple[int, int]]:
    spans: set[tuple[int, int]] = set()
    for match in function_definition_pattern.finditer(sql):
        spans.add(match.span("name"))
    return spans


def _is_dynamic_exec(name: str, options: Options) -> bool:
    normalized = _normalize_full_name(name, case_insensitive=options.case_insensitive)
    return normalized.endswith("sp_executesql")


def _resolve_target(
    name: str,
    base_name_index: dict[str, list[str]],
    node_by_id: dict[str, dict[str, str]],
    options: Options,
    object_type: str,
    ambiguous_calls: set[tuple[str, str]],
    caller_name: str,
    errors: list[dict[str, str]],
) -> str | None:
    normalized = _normalize_full_name(name, case_insensitive=options.case_insensitive)
    schema, base_name = _split_identifier(normalized, case_insensitive=False)

    def _is_target_type(target_id: str) -> bool:
        node = node_by_id.get(target_id)
        return node is not None and node["type"].lower() == object_type

    if options.schema_sensitive:
        if schema is None:
            return None
        if normalized in node_by_id and _is_target_type(normalized):
            return normalized
        return None

    if schema is not None:
        if normalized in node_by_id and _is_target_type(normalized):
            return normalized

    candidates = [item for item in base_name_index.get(base_name, []) if _is_target_type(item)]
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    key = (caller_name, base_name)
    if key not in ambiguous_calls:
        errors.append(
            {
                "id": "AMBIGUOUS_TARGET",
                "message": f"Call to {base_name} is ambiguous across schemas.",
                "object": caller_name,
            }
        )
        ambiguous_calls.add(key)
    return None


def _record_edge(
    edge_stats: dict[tuple[str, str, str], dict[str, object]],
    from_id: str,
    to_id: str,
    kind: str,
    signal: str,
) -> None:
    key = (from_id, to_id, kind)
    entry = edge_stats.get(key)
    if entry is None:
        edge_stats[key] = {
            "from": from_id,
            "to": to_id,
            "kind": kind,
            "count": 1,
            "signals": [signal],
        }
        return
    entry["count"] = int(entry["count"]) + 1
    signals = entry["signals"]
    if signal not in signals and len(signals) < SIGNAL_LIMIT:
        signals.append(signal)


def _build_edges(
    edge_stats: dict[tuple[str, str, str], dict[str, object]],
    node_by_id: dict[str, dict[str, str]],
) -> list[dict[str, object]]:
    edges: list[dict[str, object]] = []
    node_ids = set(node_by_id)
    for entry in edge_stats.values():
        if entry["from"] not in node_ids or entry["to"] not in node_ids:
            continue
        edges.append(
            {
                "from": entry["from"],
                "to": entry["to"],
                "kind": entry["kind"],
                "count": entry["count"],
                "signals": entry["signals"],
            }
        )
    return edges


def _build_topology(
    nodes: list[dict[str, str]],
    edges: list[dict[str, object]],
) -> dict[str, object]:
    in_degree = {node["id"]: 0 for node in nodes}
    out_degree = {node["id"]: 0 for node in nodes}

    for edge in edges:
        from_id = edge["from"]
        to_id = edge["to"]
        if from_id in out_degree:
            out_degree[from_id] += 1
        if to_id in in_degree:
            in_degree[to_id] += 1

    roots = sorted([node_id for node_id, degree in in_degree.items() if degree == 0])
    leaves = sorted([node_id for node_id, degree in out_degree.items() if degree == 0])

    return {
        "roots": roots,
        "leaves": leaves,
        "in_degree": in_degree,
        "out_degree": out_degree,
    }


def _detect_cycles(edges: list[dict[str, object]]) -> tuple[bool, dict[str, str] | None]:
    if importlib.util.find_spec("networkx") is None:
        return False, {
            "id": "CYCLE_DETECTION_UNAVAILABLE",
            "message": "networkx is not available; cycle detection skipped.",
        }

    import networkx as nx

    graph = nx.DiGraph()
    graph.add_edges_from([(edge["from"], edge["to"]) for edge in edges])
    return (not nx.is_directed_acyclic_graph(graph)), None


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

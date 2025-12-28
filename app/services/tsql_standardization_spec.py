from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from importlib import import_module
from importlib.util import find_spec
from typing import Any

logger = logging.getLogger(__name__)


def _load_module(module_name: str) -> Any | None:
    if find_spec(module_name) is None:
        return None
    return import_module(module_name)


_ANALYZER_MODULE = _load_module("app.services.tsql_analyzer")
_BUSINESS_RULES_MODULE = _load_module("app.services.tsql_business_rules")
_MAPPING_STRATEGY_MODULE = _load_module("app.services.tsql_mapping_strategy")
_TX_BOUNDARY_MODULE = _load_module("app.services.tsql_tx_boundary")
_DIFFICULTY_MODULE = _load_module("app.services.tsql_mybatis_difficulty")
_PERF_RISK_MODULE = _load_module("app.services.tsql_performance_risk")
_DB_DEP_MODULE = _load_module("app.services.tsql_db_dependency")


@dataclass(frozen=True)
class Options:
    dialect: str = "tsql"
    case_insensitive: bool = True
    include_sections: list[str] | None = None
    max_items_per_section: int = 50


ALL_SECTIONS = [
    "references",
    "transactions",
    "migration_impacts",
    "control_flow",
    "data_changes",
    "error_handling",
    "business_rules",
    "mybatis_strategy",
    "tx_boundary",
    "difficulty",
    "perf_risk",
    "db_dependency",
]


def build_standardization_spec(
    name: str,
    obj_type: str,
    sql: str | None,
    inputs: dict[str, Any] | None,
    options: Options,
) -> dict[str, Any]:
    include_sections = _normalize_sections(options.include_sections)
    errors: list[str] = []

    if sql is not None:
        sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
        logger.info(
            "build_standardization_spec: sql_len=%s sql_hash=%s obj_type=%s",
            len(sql),
            sql_hash,
            obj_type,
        )
    else:
        logger.info("build_standardization_spec: inputs_only obj_type=%s", obj_type)

    analyze_inputs = inputs.get("analyze") if inputs else None

    references = _resolve_section(
        "references",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "references"),
        _call_analyzer(sql, "analyze_references", [options.dialect]),
    )
    transactions = _resolve_section(
        "transactions",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "transactions"),
        _call_analyzer(sql, "analyze_transactions"),
    )
    migration_impacts = _resolve_section(
        "migration_impacts",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "migration_impacts"),
        _call_analyzer(sql, "analyze_migration_impacts"),
    )
    control_flow = _resolve_section(
        "control_flow",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "control_flow"),
        _call_analyzer(sql, "analyze_control_flow", [options.dialect]),
    )
    data_changes = _resolve_section(
        "data_changes",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "data_changes"),
        _call_analyzer(sql, "analyze_data_changes", [options.dialect]),
    )
    error_handling = _resolve_section(
        "error_handling",
        include_sections,
        errors,
        _extract_input(analyze_inputs, "error_handling"),
        _call_analyzer(sql, "analyze_error_handling"),
    )

    _extend_errors(errors, analyze_inputs)
    _extend_errors(errors, references, "errors")
    _extend_errors(errors, control_flow, "errors")
    _extend_errors(errors, data_changes, "errors")

    references = _unwrap_section(references, "references")
    control_flow = _unwrap_section(control_flow, "control_flow")
    data_changes = _unwrap_section(data_changes, "data_changes")

    business_rules = _resolve_section(
        "business_rules",
        include_sections,
        errors,
        _extract_input(inputs, "business_rules"),
        _call_module_function(
            sql,
            _BUSINESS_RULES_MODULE,
            "analyze_business_rules",
            [
                options.dialect,
                options.case_insensitive,
                options.max_items_per_section,
                options.max_items_per_section,
            ],
        ),
    )

    mapping_strategy = _resolve_section(
        "mybatis_strategy",
        include_sections,
        errors,
        _extract_input(inputs, "mybatis_strategy"),
        _call_module_function(
            sql,
            _MAPPING_STRATEGY_MODULE,
            "recommend_mapping_strategy",
            [
                obj_type,
                options.dialect,
                options.case_insensitive,
                "rewrite_to_mybatis_sql",
                options.max_items_per_section,
            ],
        ),
    )

    tx_boundary = _resolve_section(
        "tx_boundary",
        include_sections,
        errors,
        _extract_input(inputs, "tx_boundary"),
        _call_module_function(
            sql,
            _TX_BOUNDARY_MODULE,
            "recommend_transaction_boundary",
            [
                obj_type,
                options.dialect,
                options.case_insensitive,
                True,
                options.max_items_per_section,
            ],
        ),
    )

    difficulty = _resolve_section(
        "difficulty",
        include_sections,
        errors,
        _extract_input(inputs, "difficulty"),
        _call_module_function(
            sql,
            _DIFFICULTY_MODULE,
            "evaluate_mybatis_difficulty",
            [
                obj_type,
                options.dialect,
                options.case_insensitive,
                options.max_items_per_section,
            ],
        ),
    )

    perf_risk = _resolve_section(
        "perf_risk",
        include_sections,
        errors,
        _extract_input(inputs, "perf_risk"),
        _call_module_function(
            sql,
            _PERF_RISK_MODULE,
            "analyze_performance_risk",
            [
                options.dialect,
                options.case_insensitive,
                options.max_items_per_section,
            ],
        ),
    )

    db_dependency = _resolve_section(
        "db_dependency",
        include_sections,
        errors,
        _extract_input(inputs, "db_dependency"),
        _call_module_function(
            sql,
            _DB_DEP_MODULE,
            "analyze_db_dependency",
            [
                options.dialect,
                options.case_insensitive,
                False,
                options.max_items_per_section,
            ],
        ),
    )

    has_writes = _safe_get(data_changes, ["has_writes"], default=False)
    uses_transaction = _safe_get(transactions, ["uses_transaction"], default=False)
    cyclomatic_complexity = _safe_get(control_flow, ["summary", "cyclomatic_complexity"], 0)
    impact_ids = {item["id"] for item in _safe_list(migration_impacts, "items")}

    linked_servers = _linked_servers(db_dependency)
    cross_db = _cross_db(db_dependency)
    perf_risk_level = _safe_get(perf_risk, ["summary", "risk_level"], default="unknown")
    difficulty_level = _difficulty_level(mapping_strategy, difficulty)

    tags = _build_tags(
        has_writes=has_writes,
        uses_transaction=uses_transaction,
        impact_ids=impact_ids,
        cyclomatic_complexity=cyclomatic_complexity,
        linked_servers=linked_servers,
        cross_db=cross_db,
        perf_risk_level=perf_risk_level,
        difficulty_level=difficulty_level,
    )
    tags = sorted(set(tags))
    tags = _cap_list(tags, options.max_items_per_section, errors, "tags")

    templates = _build_templates(business_rules)
    templates = sorted(templates, key=lambda item: (-item["confidence"], item["id"]))
    templates = _cap_list(templates, options.max_items_per_section, errors, "templates")

    rules = _build_rules(business_rules)
    rules = sorted(rules, key=lambda item: (item["sort_key"], item["id"]))
    rules = [rule["payload"] for rule in rules]
    rules = _cap_list(rules, options.max_items_per_section, errors, "rules")

    dependencies = {
        "tables": _sorted_unique(_safe_get(references, ["tables"], default=[])),
        "functions": _sorted_unique(_safe_get(references, ["functions"], default=[])),
        "cross_db": cross_db,
        "linked_servers": linked_servers,
    }
    dependencies["tables"] = _cap_list(
        dependencies["tables"], options.max_items_per_section, errors, "dependencies.tables"
    )
    dependencies["functions"] = _cap_list(
        dependencies["functions"],
        options.max_items_per_section,
        errors,
        "dependencies.functions",
    )
    dependencies["cross_db"] = _cap_list(
        dependencies["cross_db"], options.max_items_per_section, errors, "dependencies.cross_db"
    )
    dependencies["linked_servers"] = _cap_list(
        dependencies["linked_servers"],
        options.max_items_per_section,
        errors,
        "dependencies.linked_servers",
    )

    transactions_spec = _transaction_spec(transactions, tx_boundary)
    mybatis_spec = {
        "approach": _safe_get(mapping_strategy, ["summary", "approach"], default="unknown"),
        "difficulty_score": _safe_get(difficulty, ["summary", "difficulty_score"]),
    }

    risks = {
        "migration_impacts": _sorted_unique([item["id"] for item in _safe_list(migration_impacts)]),
        "performance": _sorted_unique([item["id"] for item in _safe_list(perf_risk, "findings")]),
        "db_dependency": _sorted_unique(
            [item["id"] for item in _safe_list(db_dependency, "reasons")]
        ),
    }
    risks["migration_impacts"] = _cap_list(
        risks["migration_impacts"],
        options.max_items_per_section,
        errors,
        "risks.migration_impacts",
    )
    risks["performance"] = _cap_list(
        risks["performance"],
        options.max_items_per_section,
        errors,
        "risks.performance",
    )
    risks["db_dependency"] = _cap_list(
        risks["db_dependency"],
        options.max_items_per_section,
        errors,
        "risks.db_dependency",
    )

    recommendations = _build_recommendations(mapping_strategy, difficulty, perf_risk, db_dependency)
    recommendations = sorted(recommendations, key=lambda item: item["id"])
    recommendations = _cap_list(
        recommendations, options.max_items_per_section, errors, "recommendations"
    )

    summary = {
        "one_liner": _one_liner(
            obj_type,
            has_writes,
            cyclomatic_complexity,
            mybatis_spec["approach"],
            perf_risk_level,
            difficulty_level,
        ),
        "risk_level": perf_risk_level,
        "difficulty_level": difficulty_level,
    }

    evidence = {
        "signals": {
            "table_count": len(dependencies["tables"]),
            "cyclomatic_complexity": cyclomatic_complexity,
            "has_writes": has_writes,
            "uses_transaction": uses_transaction,
            "has_try_catch": _safe_get(error_handling, ["has_try_catch"], default=False),
        }
    }

    return {
        "version": "5.1.0",
        "object": {
            "name": name,
            "type": obj_type,
            "normalized": _normalize_name(name),
        },
        "spec": {
            "tags": tags,
            "summary": summary,
            "templates": templates,
            "rules": rules,
            "dependencies": dependencies,
            "transactions": transactions_spec,
            "mybatis": mybatis_spec,
            "risks": risks,
            "recommendations": recommendations,
            "evidence": evidence,
        },
        "errors": _sorted_unique(errors),
    }


def _normalize_sections(sections: list[str] | None) -> list[str]:
    if not sections:
        return ALL_SECTIONS[:]
    normalized = [item.strip().lower() for item in sections if item.strip()]
    return _sorted_unique(normalized)


def _extract_input(inputs: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if not inputs:
        return None
    return inputs.get(key)


def _unwrap_section(payload: dict[str, Any] | None, key: str) -> dict[str, Any] | None:
    if not payload:
        return None
    if key in payload and isinstance(payload[key], dict):
        return payload[key]
    return payload


def _extend_errors(errors: list[str], payload: dict[str, Any] | None, key: str = "errors") -> None:
    if not payload:
        return
    payload_errors = payload.get(key)
    if payload_errors:
        errors.extend(payload_errors)


def _resolve_section(
    section: str,
    include_sections: list[str],
    errors: list[str],
    input_value: dict[str, Any] | None,
    computed_value: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if input_value is not None:
        return input_value
    if computed_value is not None:
        return computed_value
    if section in include_sections:
        errors.append(f"SECTION_NOT_AVAILABLE: {section}")
    return None


def _call_analyzer(
    sql: str | None, name: str, args: list[Any] | None = None
) -> dict[str, Any] | None:
    if sql is None or _ANALYZER_MODULE is None:
        return None
    func = getattr(_ANALYZER_MODULE, name, None)
    if func is None:
        return None
    return func(sql, *(args or []))


def _call_module_function(
    sql: str | None,
    module: Any | None,
    name: str,
    args: list[Any],
) -> dict[str, Any] | None:
    if sql is None or module is None:
        return None
    func = getattr(module, name, None)
    if func is None:
        return None
    return func(sql, *args)


def _safe_get(payload: dict[str, Any] | None, path: list[str], default: Any = None) -> Any:
    if not payload:
        return default
    current: Any = payload
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def _safe_list(payload: dict[str, Any] | None, key: str | None = None) -> list[dict[str, Any]]:
    if not payload:
        return []
    if key is None:
        items = payload.get("items", [])
    else:
        items = payload.get(key, [])
    return items if isinstance(items, list) else []


def _build_templates(business_rules: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not business_rules:
        return []
    templates: list[dict[str, Any]] = []
    for item in business_rules.get("template_suggestions", []):
        templates.append(
            {
                "id": item["template_id"],
                "source": "business_rules",
                "confidence": item["confidence"],
            }
        )
    return templates


def _build_rules(business_rules: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not business_rules:
        return []
    rules: list[dict[str, Any]] = []
    for item in business_rules.get("rules", []):
        rules.append(
            {
                "payload": {
                    "id": item["id"],
                    "kind": item["kind"],
                    "condition": item["condition"],
                    "action": item["action"],
                },
                "sort_key": -item.get("confidence", 0.0),
                "id": item["id"],
            }
        )
    return rules


def _build_recommendations(*sources: dict[str, Any] | None) -> list[dict[str, Any]]:
    recommendations: dict[str, dict[str, Any]] = {}
    for source in sources:
        if not source:
            continue
        for item in source.get("recommendations", []):
            rec_id = item["id"]
            recommendations.setdefault(rec_id, {"id": rec_id, "message": item["message"]})
    return list(recommendations.values())


def _transaction_spec(
    transactions: dict[str, Any] | None, tx_boundary: dict[str, Any] | None
) -> dict[str, Any]:
    if tx_boundary:
        summary = tx_boundary.get("summary", {})
        return {
            "recommended_boundary": summary.get("recommended_boundary"),
            "propagation": summary.get("propagation"),
            "isolation_level": summary.get("isolation_level"),
        }
    if transactions:
        uses_transaction = transactions.get("uses_transaction", False)
        return {
            "recommended_boundary": "service" if uses_transaction else "none",
            "propagation": "REQUIRED" if uses_transaction else "SUPPORTS",
            "isolation_level": transactions.get("isolation_level"),
        }
    return {
        "recommended_boundary": None,
        "propagation": None,
        "isolation_level": None,
    }


def _difficulty_level(
    mapping_strategy: dict[str, Any] | None, difficulty: dict[str, Any] | None
) -> str:
    if difficulty:
        level = _safe_get(difficulty, ["summary", "difficulty_level"])
        if level:
            return level
    mapping_level = _safe_get(mapping_strategy, ["summary", "difficulty"])
    return mapping_level or "unknown"


def _build_tags(
    *,
    has_writes: bool,
    uses_transaction: bool,
    impact_ids: set[str],
    cyclomatic_complexity: int,
    linked_servers: list[str],
    cross_db: list[str],
    perf_risk_level: str,
    difficulty_level: str,
) -> list[str]:
    tags: list[str] = []
    tags.append("has_writes" if has_writes else "read_only")
    tags.append("uses_transaction" if uses_transaction else "no_txn")

    if "IMP_DYN_SQL" in impact_ids:
        tags.append("dynamic_sql")
    if "IMP_CURSOR" in impact_ids:
        tags.append("cursor")
    if {"IMP_TEMP_TABLE", "IMP_TABLE_VARIABLE"} & impact_ids:
        tags.append("temp_objects")
    if "IMP_MERGE" in impact_ids:
        tags.append("merge")

    if cyclomatic_complexity <= 5:
        tags.append("low_complexity")
    elif cyclomatic_complexity >= 12:
        tags.append("high_complexity")

    if linked_servers:
        tags.append("linked_server")
    if cross_db:
        tags.append("cross_db")

    if perf_risk_level in {"high", "critical"}:
        tags.append("perf_risk_high")
    if difficulty_level in {"high", "very_high"}:
        tags.append("difficulty_high")

    return tags


def _one_liner(
    obj_type: str,
    has_writes: bool,
    cyclomatic_complexity: int,
    approach: str,
    risk_level: str,
    difficulty_level: str,
) -> str:
    read_phrase = "Read-only" if not has_writes else "Write-enabled"
    complexity_phrase = "low complexity" if cyclomatic_complexity <= 5 else "moderate complexity"
    if cyclomatic_complexity >= 12:
        complexity_phrase = "high complexity"

    approach_phrase = "migration approach undetermined"
    if approach == "rewrite_to_mybatis_sql":
        approach_phrase = "safe for MyBatis rewrite"
    elif approach == "call_sp_first":
        approach_phrase = "best suited for call-first migration"

    normalized_type = obj_type.lower()
    return (
        f"{read_phrase} {normalized_type} with {complexity_phrase}; "
        f"{approach_phrase}; risk {risk_level}, difficulty {difficulty_level}."
    )


def _linked_servers(db_dependency: dict[str, Any] | None) -> list[str]:
    if not db_dependency:
        return []
    linked_servers = db_dependency.get("dependencies", {}).get("linked_servers", [])
    servers = [item["server"] for item in linked_servers if "server" in item]
    return _sorted_unique(servers)


def _cross_db(db_dependency: dict[str, Any] | None) -> list[str]:
    if not db_dependency:
        return []
    cross_db = db_dependency.get("dependencies", {}).get("cross_database", [])
    names = [
        f"{item['database']}.{item['schema']}.{item['object']}"
        for item in cross_db
        if all(key in item for key in ["database", "schema", "object"])
    ]
    return _sorted_unique(names)


def _normalize_name(name: str) -> str:
    return name.replace("[", "").replace("]", "").strip().lower()


def _sorted_unique(items: list[Any]) -> list[Any]:
    seen: set[Any] = set()
    deduped: list[Any] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return sorted(deduped)


def _cap_list(items: list[Any], max_items: int, errors: list[str], section_name: str) -> list[Any]:
    if max_items <= 0 or len(items) <= max_items:
        return items
    errors.append(f"SECTION_TRUNCATED: {section_name}")
    return items[:max_items]

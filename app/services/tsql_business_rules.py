from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from app.services.safe_sql import summarize_sql

logger = logging.getLogger(__name__)

MAX_SIGNAL_ITEMS = 15
MAX_CONDITION_LENGTH = 160


@dataclass(frozen=True)
class Rule:
    id: str
    kind: str
    confidence: float
    condition: str
    action: str
    signals: list[str]


@dataclass(frozen=True)
class TemplateSuggestion:
    rule_id: str
    template_id: str
    confidence: float
    rationale: str


TEMPLATE_REGISTRY: dict[str, str] = {
    "TPL_VALIDATE_REQUIRED_PARAM": "Null/empty guard + error signaling maps to required-parameter validation.",
    "TPL_VALIDATE_RANGE": "Range check maps to parameter validation rules.",
    "TPL_ENSURE_EXISTS": "Existence check with error/return signaling maps to ensure-exists behavior.",
    "TPL_ENSURE_NOT_EXISTS": "Non-existence check with error/return signaling maps to ensure-not-exists behavior.",
    "TPL_SOFT_DELETE_FILTER": "Soft-delete predicate maps to soft-delete filtering.",
    "TPL_STATUS_FILTER": "Status predicate maps to status-based filtering.",
    "TPL_CASE_TO_ENUM_MAPPING": "CASE mapping aligns with enum/flag translation.",
    "TPL_ERROR_TO_EXCEPTION": "Error signaling maps to exception translation.",
}


def analyze_business_rules(
    sql: str,
    dialect: str = "tsql",
    case_insensitive: bool = True,
    max_rules: int = 100,
    max_templates: int = 150,
) -> dict:
    summary = summarize_sql(sql)
    logger.info(
        "analyze_business_rules: sql_len=%s sql_hash=%s dialect=%s",
        summary["len"],
        summary["sha256_8"],
        dialect,
    )

    cleaned = _preprocess_sql(sql)
    rules: list[Rule] = []
    signals: list[str] = []

    rule_counter = 0
    flags = re.IGNORECASE if case_insensitive else 0

    for match in _iter_if_conditions(cleaned, flags):
        condition = match.condition
        action = _action_from_window(cleaned, match.end, flags)
        action_signal = _action_signal(action)
        action_triggers = action in {"raise_error", "return_code"}

        if _is_exists_condition(condition, flags):
            rule_counter += 1
            exists_kind = "not_exists_check" if _is_not_exists(condition, flags) else "exists_check"
            confidence = 0.8
            rule_signals = ["IF", "EXISTS"]
            if exists_kind == "not_exists_check":
                rule_signals.append("NOT")
            if action_signal:
                rule_signals.append(action_signal)
            rules.append(
                Rule(
                    id=_rule_id(rule_counter),
                    kind=exists_kind,
                    confidence=confidence,
                    condition="NOT EXISTS (SELECT …)"
                    if exists_kind == "not_exists_check"
                    else "EXISTS (SELECT …)",
                    action=action,
                    signals=rule_signals,
                )
            )
            signals.extend(rule_signals)
            continue

        if _is_guard_condition(condition, flags):
            rule_counter += 1
            confidence = 0.85 if action_triggers else 0.65
            guard_signals = _guard_signals(condition, flags)
            if action_signal:
                guard_signals.append(action_signal)
            rules.append(
                Rule(
                    id=_rule_id(rule_counter),
                    kind="guard_clause",
                    confidence=confidence,
                    condition=_sanitize_condition(condition),
                    action=action,
                    signals=guard_signals,
                )
            )
            signals.extend(guard_signals)
            continue

        range_result = _is_range_condition(condition, flags)
        if range_result:
            rule_counter += 1
            confidence = 0.75 if range_result == "clear" else 0.6
            range_signals = ["IF", "RANGE"]
            if action_signal:
                range_signals.append(action_signal)
            rules.append(
                Rule(
                    id=_rule_id(rule_counter),
                    kind="range_check",
                    confidence=confidence,
                    condition=_sanitize_condition(condition),
                    action=action,
                    signals=range_signals,
                )
            )
            signals.extend(range_signals)

    soft_delete_rules = _detect_soft_delete_filters(cleaned, rule_counter, flags)
    if soft_delete_rules:
        rule_counter = int(soft_delete_rules[-1].id[1:])
        rules.extend(soft_delete_rules)
        for rule in soft_delete_rules:
            signals.extend(rule.signals)

    status_rules = _detect_status_filters(cleaned, rule_counter, flags)
    if status_rules:
        rule_counter = int(status_rules[-1].id[1:])
        rules.extend(status_rules)
        for rule in status_rules:
            signals.extend(rule.signals)

    case_rules = _detect_case_mappings(cleaned, rule_counter, flags)
    if case_rules:
        rules.extend(case_rules)
        for rule in case_rules:
            signals.extend(rule.signals)

    errors: list[str] = []
    truncated = False

    sorted_rules = sorted(rules, key=lambda item: (-item.confidence, item.id))
    if len(sorted_rules) > max_rules:
        sorted_rules = sorted_rules[:max_rules]
        truncated = True
        errors.append("Rule list truncated to max_rules limit.")

    template_suggestions = _map_templates(sorted_rules)
    template_suggestions = sorted(
        template_suggestions,
        key=lambda item: (-item.confidence, item.rule_id, item.template_id),
    )

    if len(template_suggestions) > max_templates:
        template_suggestions = template_suggestions[:max_templates]
        truncated = True
        errors.append("Template suggestions truncated to max_templates limit.")

    signal_list = _dedupe_signals(signals)

    return {
        "version": "2.3.0",
        "summary": {
            "has_rules": bool(sorted_rules),
            "rule_count": len(sorted_rules),
            "template_suggestion_count": len(template_suggestions),
            "truncated": truncated,
        },
        "rules": [rule.__dict__ for rule in sorted_rules],
        "template_suggestions": [item.__dict__ for item in template_suggestions],
        "signals": signal_list,
        "errors": errors,
    }


def _preprocess_sql(sql: str) -> str:
    without_strings = re.sub(r"'(?:''|[^'])*'", "'?'", sql)
    without_block_comments = re.sub(r"/\*.*?\*/", " ", without_strings, flags=re.DOTALL)
    without_line_comments = re.sub(r"--.*?$", " ", without_block_comments, flags=re.MULTILINE)
    normalized_identifiers = re.sub(r"\[([^\]]+)\]", r"\1", without_line_comments)
    return re.sub(r"\s+", " ", normalized_identifiers).strip()


@dataclass(frozen=True)
class IfConditionMatch:
    condition: str
    end: int


def _iter_if_conditions(sql: str, flags: int) -> list[IfConditionMatch]:
    matches: list[IfConditionMatch] = []
    pattern = re.compile(
        r"\bIF\s+(?P<cond>.+?)(?=\bBEGIN\b|\bTHROW\b|\bRAISERROR\b|\bRETURN\b|\bELSE\b)",
        flags,
    )
    for match in pattern.finditer(sql):
        matches.append(IfConditionMatch(condition=match.group("cond").strip(), end=match.end()))
    return matches


def _is_guard_condition(condition: str, flags: int) -> bool:
    null_check = re.search(r"\bIS\s+NULL\b", condition, flags)
    empty_string = re.search(r"=\s*'\\?'|=\s*''", condition)
    len_zero = re.search(r"\bLEN\s*\(\s*@\w+\s*\)\s*=\s*0\b", condition, flags)
    nullif_check = re.search(
        r"\bNULLIF\s*\(\s*@\w+\s*,\s*'\\?'\s*\)\s+IS\s+NULL\b",
        condition,
        flags,
    )
    return bool(null_check or empty_string or len_zero or nullif_check)


def _guard_signals(condition: str, flags: int) -> list[str]:
    signals = ["IF"]
    if re.search(r"\bIS\s+NULL\b", condition, flags):
        signals.append("IS NULL")
    if re.search(r"\bLEN\s*\(", condition, flags):
        signals.append("LEN")
    if re.search(r"\bNULLIF\s*\(", condition, flags):
        signals.append("NULLIF")
    if re.search(r"=\s*'\\?'|=\s*''", condition):
        signals.append("EMPTY")
    return signals


def _is_range_condition(condition: str, flags: int) -> str | None:
    comparison = re.search(
        r"@[\w]+\s*(<=|>=|<|>)\s*-?\d+(?:\.\d+)?",
        condition,
        flags,
    )
    between = re.search(
        r"@[\w]+\s+BETWEEN\s+-?\d+(?:\.\d+)?\s+AND\s+-?\d+(?:\.\d+)?",
        condition,
        flags,
    )
    if comparison or between:
        return "clear"
    if re.search(r"@[\w]+\s*(<=|>=|<|>)\s*@", condition, flags):
        return "fuzzy"
    return None


def _is_exists_condition(condition: str, flags: int) -> bool:
    return bool(re.search(r"\bEXISTS\s*\(", condition, flags))


def _is_not_exists(condition: str, flags: int) -> bool:
    return bool(re.search(r"\bNOT\s+EXISTS\b", condition, flags))


def _action_from_window(sql: str, start: int, flags: int) -> str:
    window = sql[start : start + 220]
    if re.search(r"\bTHROW\b|\bRAISERROR\b", window, flags):
        return "raise_error"
    if re.search(r"\bRETURN\s+-?\d+\b", window, flags):
        return "return_code"
    return "branch"


def _action_signal(action: str) -> str | None:
    if action == "raise_error":
        return "THROW"
    if action == "return_code":
        return "RETURN"
    return None


def _sanitize_condition(condition: str) -> str:
    sanitized = re.sub(r"'(?:''|[^'])*'", "'?'", condition)
    sanitized = re.sub(r"\b-?\d+(?:\.\d+)?\b", "?", sanitized)
    sanitized = re.sub(r"\bSELECT\b.*", "SELECT …", sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    if len(sanitized) > MAX_CONDITION_LENGTH:
        sanitized = f"{sanitized[: MAX_CONDITION_LENGTH - 1]}…"
    return sanitized


def _rule_id(counter: int) -> str:
    return f"R{counter:03d}"


def _detect_soft_delete_filters(sql: str, counter: int, flags: int) -> list[Rule]:
    patterns = [
        (r"\bis_deleted\s*=\s*0\b", "is_deleted = ?"),
        (r"\bdeleted_yn\s*=\s*'\\?'\b", "deleted_yn = ?"),
        (r"\bdel_yn\s*=\s*'\\?'\b", "del_yn = ?"),
    ]
    return _detect_predicate_rules(sql, counter, patterns, "soft_delete_filter", flags)


def _detect_status_filters(sql: str, counter: int, flags: int) -> list[Rule]:
    patterns = [
        (r"\buse_yn\s*=\s*'\\?'\b", "use_yn = ?"),
        (r"\bactive_yn\s*=\s*'\\?'\b", "active_yn = ?"),
        (r"\bstatus\s*=\s*'\\?'\b", "status = ?"),
    ]
    return _detect_predicate_rules(sql, counter, patterns, "status_filter", flags)


def _detect_predicate_rules(
    sql: str,
    counter: int,
    patterns: list[tuple[str, str]],
    kind: str,
    flags: int,
) -> list[Rule]:
    found: list[Rule] = []
    seen_conditions: set[str] = set()
    for pattern, condition in patterns:
        if re.search(pattern, sql, flags):
            if condition in seen_conditions:
                continue
            seen_conditions.add(condition)
            counter += 1
            signals = ["FILTER", "PREDICATE"]
            found.append(
                Rule(
                    id=_rule_id(counter),
                    kind=kind,
                    confidence=0.7,
                    condition=condition,
                    action="filter",
                    signals=signals,
                )
            )
    return found


def _detect_case_mappings(sql: str, counter: int, flags: int) -> list[Rule]:
    matches = list(re.finditer(r"\bCASE\b", sql, flags))
    if not matches:
        return []
    found: list[Rule] = []
    for match in matches:
        window = sql[match.start() : match.start() + 120]
        expr_match = re.search(r"\bCASE\s+(?P<expr>.+?)\s+WHEN\b", window, flags)
        expr = expr_match.group("expr").strip() if expr_match else ""
        headline = f"CASE mapping on {expr}" if expr else "CASE mapping"
        mapped_confidence = 0.65
        if re.search(r"\b(status|active|use_yn|del_yn)\b", expr, flags):
            mapped_confidence = 0.75
        counter += 1
        found.append(
            Rule(
                id=_rule_id(counter),
                kind="case_mapping",
                confidence=mapped_confidence,
                condition=_sanitize_condition(headline),
                action="mapping",
                signals=["CASE", "WHEN", "THEN"],
            )
        )
    return found


def _map_templates(rules: list[Rule]) -> list[TemplateSuggestion]:
    suggestions: list[TemplateSuggestion] = []
    for rule in rules:
        primary = _primary_template(rule)
        if primary:
            confidence = max(0.75, min(0.9, rule.confidence))
            suggestions.append(
                TemplateSuggestion(
                    rule_id=rule.id,
                    template_id=primary,
                    confidence=confidence,
                    rationale=TEMPLATE_REGISTRY[primary],
                )
            )
        if rule.action == "raise_error":
            suggestions.append(
                TemplateSuggestion(
                    rule_id=rule.id,
                    template_id="TPL_ERROR_TO_EXCEPTION",
                    confidence=0.6,
                    rationale=TEMPLATE_REGISTRY["TPL_ERROR_TO_EXCEPTION"],
                )
            )
    return suggestions


def _primary_template(rule: Rule) -> str | None:
    if rule.kind == "guard_clause":
        return "TPL_VALIDATE_REQUIRED_PARAM"
    if rule.kind == "range_check":
        return "TPL_VALIDATE_RANGE"
    if rule.kind == "exists_check" and rule.action in {"raise_error", "return_code"}:
        return "TPL_ENSURE_EXISTS"
    if rule.kind == "not_exists_check" and rule.action in {"raise_error", "return_code"}:
        return "TPL_ENSURE_NOT_EXISTS"
    if rule.kind == "soft_delete_filter":
        return "TPL_SOFT_DELETE_FILTER"
    if rule.kind == "status_filter":
        return "TPL_STATUS_FILTER"
    if rule.kind == "case_mapping":
        return "TPL_CASE_TO_ENUM_MAPPING"
    return None


def _dedupe_signals(signals: list[str]) -> list[str]:
    flattened: list[str] = []
    for signal in signals:
        if isinstance(signal, list):
            flattened.extend(signal)
        else:
            flattened.append(signal)
    unique = sorted(set(flattened))
    return unique[:MAX_SIGNAL_ITEMS]

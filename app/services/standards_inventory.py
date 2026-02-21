from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.services import rag_lexical
from app.services.rag_lexical import load_documents
from app.services.tsql_business_rules import TEMPLATE_REGISTRY

ROOT_DIR = Path(__file__).resolve().parents[2]

TAG_IDS = [
    "cross_db",
    "cursor",
    "difficulty_high",
    "dynamic_sql",
    "has_writes",
    "high_complexity",
    "linked_server",
    "low_complexity",
    "merge",
    "no_txn",
    "perf_risk_high",
    "read_only",
    "temp_objects",
    "uses_transaction",
]

_PATTERN_KEYWORDS: dict[str, list[str]] = {
    "PAT_MYBATIS_DYNAMIC_TAGS": ["dynamic", "sql", "mybatis", "if", "choose", "foreach"],
    "PAT_REPLACE_CURSOR_SET_BASED": ["cursor", "set", "based", "set-based"],
    "PAT_SERVICE_LAYER_TX": ["transaction", "service", "boundary", "transactional"],
    "PAT_ISOLATE_EXTERNAL_INTEGRATION": [
        "linked",
        "server",
        "cross",
        "database",
        "integration",
        "external",
    ],
    "PAT_AVOID_SELECT_STAR": ["select", "columns", "explicit"],
}


@dataclass(frozen=True)
class CoverageResult:
    identifier: str
    covered: bool
    ambiguous: bool
    chunk_hits: int
    source_hits: int


def _source_text(module_path: str) -> str:
    path = ROOT_DIR / module_path
    return path.read_text(encoding="utf-8")


def _extract_prefixed_ids(module_path: str, prefix: str) -> list[str]:
    text = _source_text(module_path)
    matches = re.findall(rf'"({prefix}[A-Z0-9_]+)"', text)
    return sorted(set(matches))


def collect_inventory() -> dict[str, Any]:
    migration_risk_ids = _extract_prefixed_ids("app/services/tsql_analyzer.py", "IMP_")
    performance_risk_ids = _extract_prefixed_ids("app/services/tsql_performance_risk.py", "PRF_")
    db_dependency_risk_ids = _extract_prefixed_ids("app/services/tsql_db_dependency.py", "RSN_")
    template_ids = sorted(TEMPLATE_REGISTRY.keys())

    return {
        "tags": TAG_IDS,
        "risks": {
            "migration_impacts": migration_risk_ids,
            "performance": performance_risk_ids,
            "db_dependency": db_dependency_risk_ids,
        },
        "templates": template_ids,
        "patterns": [
            {"id": pattern_id, "keywords": keywords}
            for pattern_id, keywords in sorted(_PATTERN_KEYWORDS.items())
        ],
    }


def _is_heading_only_hit(chunk_text: str, token: str) -> bool:
    lines = [line.strip() for line in chunk_text.splitlines() if line.strip()]
    if not lines:
        return False
    first = lines[0].lower()
    token_lower = token.lower()
    if token_lower not in first:
        return False
    body = "\n".join(lines[1:]).lower()
    return token_lower not in body


def _token_coverage(token: str, chunks: list[rag_lexical.DocChunk]) -> CoverageResult:
    token_lower = token.lower()
    chunk_hits = 0
    heading_only = 0
    source_hits = 0

    for chunk in chunks:
        text = chunk.text.lower()
        source = Path(chunk.source).name.lower()
        in_chunk = token_lower in text
        if in_chunk:
            chunk_hits += 1
            if _is_heading_only_hit(chunk.text, token):
                heading_only += 1
        if token_lower in source:
            source_hits += 1

    covered = chunk_hits > 0
    ambiguous = covered and heading_only == chunk_hits
    if not covered and source_hits > 0:
        ambiguous = True

    return CoverageResult(
        identifier=token,
        covered=covered,
        ambiguous=ambiguous,
        chunk_hits=chunk_hits,
        source_hits=source_hits,
    )


def scan_standards_coverage(docs_dir: str) -> dict[str, Any]:
    chunks = load_documents(docs_dir)
    inventory = collect_inventory()

    categories: dict[str, list[str]] = {
        "tags": inventory["tags"],
        "risk_ids": (
            inventory["risks"]["migration_impacts"]
            + inventory["risks"]["performance"]
            + inventory["risks"]["db_dependency"]
        ),
        "template_ids": inventory["templates"],
        "pattern_ids": [item["id"] for item in inventory["patterns"]],
        "pattern_keywords": sorted(
            {keyword for item in inventory["patterns"] for keyword in item["keywords"]}
        ),
    }

    coverage: dict[str, Any] = {}
    for category, identifiers in categories.items():
        results = [_token_coverage(identifier, chunks) for identifier in identifiers]
        coverage[category] = {
            "total": len(results),
            "covered": sum(1 for result in results if result.covered),
            "missing": sum(1 for result in results if not result.covered),
            "ambiguous": sum(1 for result in results if result.ambiguous),
            "items": [result.__dict__ for result in results],
        }

    return {
        "docs_dir": docs_dir,
        "chunk_count": len(chunks),
        "inventory": inventory,
        "coverage": coverage,
    }


def save_inventory(path: str) -> None:
    data = collect_inventory()
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _missing_rows(coverage: dict[str, object], category: str) -> list[dict[str, object]]:
    section = coverage[category]
    return [item for item in section["items"] if not item["covered"]]


def _recommended_doc(identifier: str, category: str) -> str:
    if category == "tags":
        return "standards/10_tags.md"
    if category == "risk_ids":
        if identifier.startswith("IMP_"):
            return "standards/20_migration_impacts.md"
        if identifier.startswith("PRF_"):
            return "standards/50_performance_risks.md"
        return "standards/30_db_dependency.md"
    if category == "template_ids":
        return "standards/40_templates.md"
    return f"standards/patterns/{identifier}.md"


def main() -> None:
    from app.services.standards_inventory import scan_standards_coverage

    report_path = Path("standards/_report.md")
    data = scan_standards_coverage("standards")
    coverage = data["coverage"]

    lines: list[str] = []
    lines.append("# Standards Coverage Report")
    lines.append("")
    lines.append(f"Generated at: {datetime.now(UTC).isoformat()}")
    lines.append(f"Docs directory: {data['docs_dir']}")
    lines.append(f"Chunk count: {data['chunk_count']}")
    lines.append("")
    lines.append("## Coverage Summary")
    lines.append("")
    lines.append("| Category | Total | Covered | Missing | Ambiguous |")
    lines.append("|---|---:|---:|---:|---:|")
    for category in ["tags", "risk_ids", "template_ids", "pattern_ids", "pattern_keywords"]:
        section = coverage[category]
        lines.append(
            f"| {category} | {section['total']} | {section['covered']} | {section['missing']} | {section['ambiguous']} |"
        )

    lines.append("")
    lines.append("## Missing Identifiers")
    lines.append("")
    lines.append("| Category | Identifier | Recommended doc target |")
    lines.append("|---|---|---|")
    for category in ["tags", "risk_ids", "template_ids", "pattern_ids", "pattern_keywords"]:
        missing = _missing_rows(coverage, category)
        for item in missing:
            identifier = item["identifier"]
            lines.append(
                f"| {category} | {identifier} | {_recommended_doc(identifier, category)} |"
            )

    lines.append("")
    lines.append("## Notes")
    lines.append("")
    lines.append("- Coverage uses `app.services.rag_lexical.load_documents` chunking behavior.")
    lines.append(
        "- Query-term tokenization splits identifiers on `_`, `-`, and `.`; include exact IDs and useful split keywords in docs."
    )
    lines.append(
        "- `ambiguous` means identifier appears only in headings or file names (or heading-only chunks), which may reduce retrieval quality."
    )

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

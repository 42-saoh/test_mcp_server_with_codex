from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TOKEN_PATTERN = re.compile(r"\w+", re.UNICODE)
SUPPORTED_EXTENSIONS = {".md", ".txt"}


@dataclass(frozen=True)
class DocChunk:
    doc_id: str
    title: str
    source: str
    text: str
    chunk_id: int


@dataclass(frozen=True)
class Index:
    chunks: list[DocChunk]
    vectors: list[dict[str, float]]
    norms: list[float]
    idf: dict[str, float]
    case_insensitive: bool


@dataclass(frozen=True)
class Hit:
    doc_id: str
    title: str
    source: str
    score: float
    text: str


def load_documents(docs_dir: str) -> list[DocChunk]:
    root = Path(docs_dir)
    if not root.exists() or not root.is_dir():
        return []

    files = sorted(
        {path for path in root.rglob("*") if path.suffix.lower() in SUPPORTED_EXTENSIONS}
    )
    chunks: list[DocChunk] = []
    for doc_index, path in enumerate(files, start=1):
        text = path.read_text(encoding="utf-8", errors="replace")
        title = _extract_title(path, text)
        for chunk_index, chunk_text in enumerate(_chunk_text(path.suffix.lower(), text), start=1):
            cleaned = chunk_text.strip()
            if not cleaned:
                continue
            doc_id = f"doc_{doc_index:04d}#chunk_{chunk_index:04d}"
            chunks.append(
                DocChunk(
                    doc_id=doc_id,
                    title=title,
                    source=str(path),
                    text=cleaned,
                    chunk_id=chunk_index,
                )
            )
    return chunks


def build_index(chunks: list[DocChunk], *, case_insensitive: bool = True) -> Index:
    if not chunks:
        return Index(chunks=[], vectors=[], norms=[], idf={}, case_insensitive=case_insensitive)

    tokenized = [_tokenize(chunk.text, case_insensitive=case_insensitive) for chunk in chunks]
    df: Counter[str] = Counter()
    for tokens in tokenized:
        df.update(set(tokens))

    total_docs = len(chunks)
    idf = {term: math.log((total_docs + 1) / (count + 1)) + 1 for term, count in df.items()}

    vectors: list[dict[str, float]] = []
    norms: list[float] = []
    for tokens in tokenized:
        tf = Counter(tokens)
        weights = {term: (1.0 + math.log(freq)) * idf.get(term, 0.0) for term, freq in tf.items()}
        norm = math.sqrt(sum(weight * weight for weight in weights.values()))
        vectors.append(weights)
        norms.append(norm)

    return Index(
        chunks=chunks, vectors=vectors, norms=norms, idf=idf, case_insensitive=case_insensitive
    )


def search(index: Index, query: str, top_k: int) -> list[Hit]:
    if not query.strip():
        return []

    query_tokens = _tokenize(query, case_insensitive=index.case_insensitive)
    if not query_tokens:
        return []

    tf = Counter(query_tokens)
    query_weights = {
        term: (1.0 + math.log(freq)) * index.idf.get(term, 0.0) for term, freq in tf.items()
    }
    query_norm = math.sqrt(sum(weight * weight for weight in query_weights.values()))
    if query_norm == 0:
        return []

    hits: list[Hit] = []
    for chunk, vector, norm in zip(index.chunks, index.vectors, index.norms, strict=True):
        if norm == 0:
            continue
        dot = sum(query_weights.get(term, 0.0) * vector.get(term, 0.0) for term in query_weights)
        if dot <= 0:
            continue
        score = dot / (query_norm * norm)
        hits.append(
            Hit(
                doc_id=chunk.doc_id,
                title=chunk.title,
                source=chunk.source,
                score=score,
                text=chunk.text,
            )
        )

    hits.sort(key=lambda item: (-item.score, item.doc_id))
    return hits[: max(top_k, 0)]


def extract_query_terms(spec: dict[str, Any]) -> list[str]:
    terms: list[str] = []
    for tag in spec.get("tags", []):
        terms.append(str(tag))
    for template in spec.get("templates", []):
        if isinstance(template, dict) and template.get("id"):
            terms.append(str(template["id"]))
    risks = spec.get("risks", {}) if isinstance(spec.get("risks", {}), dict) else {}
    for key in ("migration_impacts", "performance", "db_dependency"):
        for item in risks.get(key, []):
            terms.append(str(item))

    normalized = [_normalize_term(term) for term in terms]
    return _sorted_unique(normalized)[:30]


def build_snippet(text: str, max_chars: int) -> tuple[str, bool]:
    cleaned = " ".join(text.split())
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned, False
    return cleaned[:max_chars].rstrip(), True


def build_pattern_recommendations(
    spec: dict[str, Any],
    hits: list[Hit],
) -> list[dict[str, Any]]:
    tags = set(spec.get("tags", []))
    template_ids = {item.get("id") for item in spec.get("templates", []) if isinstance(item, dict)}
    risk_ids = set()
    risks = spec.get("risks", {})
    if isinstance(risks, dict):
        for key in ("migration_impacts", "performance", "db_dependency"):
            risk_ids.update(risks.get(key, []))

    recommendations: list[dict[str, Any]] = []

    def add_recommendation(rec_id: str, message: str, keywords: Iterable[str]) -> None:
        source_doc_id = _best_doc_for_keywords(hits, keywords)
        recommendations.append({"id": rec_id, "message": message, "source_doc_id": source_doc_id})

    if "dynamic_sql" in tags or _template_matches(template_ids, "DYNAMIC"):
        add_recommendation(
            "PAT_MYBATIS_DYNAMIC_TAGS",
            "Prefer MyBatis <if>/<choose>/<foreach> over concatenated dynamic SQL.",
            ["dynamic", "sql", "mybatis", "if", "choose", "foreach"],
        )

    if "cursor" in tags:
        add_recommendation(
            "PAT_REPLACE_CURSOR_SET_BASED",
            "Replace cursors with set-based queries or batched operations.",
            ["cursor", "set", "based", "set-based"],
        )

    if "uses_transaction" in tags:
        add_recommendation(
            "PAT_SERVICE_LAYER_TX",
            "Move transaction boundaries to the service layer with @Transactional.",
            ["transaction", "service", "boundary", "transactional"],
        )

    if {"linked_server", "cross_db"} & tags:
        add_recommendation(
            "PAT_ISOLATE_EXTERNAL_INTEGRATION",
            "Isolate linked server or cross-database access behind integration adapters.",
            ["linked", "server", "cross", "database", "integration", "external"],
        )

    if _risk_matches(risk_ids, "SELECT_STAR"):
        add_recommendation(
            "PAT_AVOID_SELECT_STAR",
            "Avoid SELECT * by listing explicit columns.",
            ["select", "columns", "explicit"],
        )

    recommendations.sort(key=lambda item: item["id"])
    return recommendations


def _template_matches(template_ids: set[str], keyword: str) -> bool:
    keyword_upper = keyword.upper()
    for template_id in template_ids:
        if not template_id:
            continue
        template_upper = str(template_id).upper()
        if template_upper.startswith("TPL_") and keyword_upper in template_upper:
            return True
    return False


def _risk_matches(risk_ids: Iterable[str], keyword: str) -> bool:
    keyword_upper = keyword.upper()
    return any(keyword_upper in str(risk_id).upper() for risk_id in risk_ids)


def _best_doc_for_keywords(hits: list[Hit], keywords: Iterable[str]) -> str | None:
    normalized_keywords = [_normalize_term(word) for word in keywords if word]
    best_score = 0
    best_doc_id: str | None = None
    for hit in hits:
        content = _normalize_term(f"{hit.title} {hit.text}")
        score = sum(1 for word in normalized_keywords if word and word in content)
        if score < 2:
            continue
        if score > best_score or (score == best_score and hit.doc_id < (best_doc_id or "")):
            best_score = score
            best_doc_id = hit.doc_id
    return best_doc_id


def _tokenize(text: str, *, case_insensitive: bool) -> list[str]:
    if case_insensitive:
        text = text.lower()
    return TOKEN_PATTERN.findall(text)


def _extract_title(path: Path, text: str) -> str:
    if path.suffix.lower() == ".md":
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title
    return path.name


def _chunk_text(extension: str, text: str) -> list[str]:
    if extension == ".md":
        return _chunk_markdown(text)
    return _chunk_plaintext(text)


def _chunk_markdown(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            if current:
                chunks.append("\n".join(current))
                current = []
            current.append(line)
            continue
        if not stripped:
            if current:
                chunks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _chunk_plaintext(text: str) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if not line.strip():
            if current:
                chunks.append("\n".join(current))
                current = []
            continue
        current.append(line)
    if current:
        chunks.append("\n".join(current))
    return chunks


def _normalize_term(term: str) -> str:
    normalized = term.strip().lower()
    return normalized


def _sorted_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return sorted(deduped)

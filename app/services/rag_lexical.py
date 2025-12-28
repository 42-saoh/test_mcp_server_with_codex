# [파일 설명]
# - 목적: 문서 조각을 기반으로 한 간단한 RAG 검색 유틸을 제공한다.
# - 제공 기능: 인덱스 구축, 쿼리 용어 추출, 검색 및 스니펫 생성 기능을 제공한다.
# - 입력/출력: 문서 목록과 쿼리를 받아 검색 결과/추천을 반환한다.
# - 주의 사항: 외부 네트워크 없이 로컬 텍스트만 처리한다.
# - 연관 모듈: 표준화 명세 생성(app.services.tsql_standardization_spec)에서 사용된다.
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


# [클래스 설명]
# - 역할: DocChunk 데이터 모델/구성 요소을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
@dataclass(frozen=True)
class DocChunk:
    doc_id: str
    title: str
    source: str
    text: str
    chunk_id: int


# [클래스 설명]
# - 역할: Index 데이터 모델/구성 요소을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
@dataclass(frozen=True)
class Index:
    chunks: list[DocChunk]
    vectors: list[dict[str, float]]
    norms: list[float]
    idf: dict[str, float]
    case_insensitive: bool


# [클래스 설명]
# - 역할: Hit 데이터 모델/구성 요소을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
@dataclass(frozen=True)
class Hit:
    doc_id: str
    title: str
    source: str
    score: float
    text: str


# [함수 설명]
# - 목적: load_documents 처리 로직을 수행한다.
# - 입력: docs_dir: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: build_index 처리 로직을 수행한다.
# - 입력: chunks: list[DocChunk], *, case_insensitive: bool = True
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: search 처리 로직을 수행한다.
# - 입력: index: Index, query: str, top_k: int
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: extract_query_terms 처리 로직을 수행한다.
# - 입력: spec: dict[str, Any]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: build_snippet 처리 로직을 수행한다.
# - 입력: text: str, max_chars: int
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def build_snippet(text: str, max_chars: int) -> tuple[str, bool]:
    cleaned = " ".join(text.split())
    if max_chars <= 0 or len(cleaned) <= max_chars:
        return cleaned, False
    return cleaned[:max_chars].rstrip(), True


# [함수 설명]
# - 목적: build_pattern_recommendations 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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

    # [함수 설명]
    # - 목적: add_recommendation 처리 로직을 수행한다.
    # - 입력: rec_id: str, message: str, keywords: Iterable[str]
    # - 출력: 구조화된 dict 결과를 반환한다.
    # - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
    # - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
    # - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: _template_matches 처리 로직을 수행한다.
# - 입력: template_ids: set[str], keyword: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _template_matches(template_ids: set[str], keyword: str) -> bool:
    keyword_upper = keyword.upper()
    for template_id in template_ids:
        if not template_id:
            continue
        template_upper = str(template_id).upper()
        if template_upper.startswith("TPL_") and keyword_upper in template_upper:
            return True
    return False


# [함수 설명]
# - 목적: _risk_matches 처리 로직을 수행한다.
# - 입력: risk_ids: Iterable[str], keyword: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _risk_matches(risk_ids: Iterable[str], keyword: str) -> bool:
    keyword_upper = keyword.upper()
    return any(keyword_upper in str(risk_id).upper() for risk_id in risk_ids)


# [함수 설명]
# - 목적: _best_doc_for_keywords 처리 로직을 수행한다.
# - 입력: hits: list[Hit], keywords: Iterable[str]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: _tokenize 처리 로직을 수행한다.
# - 입력: text: str, *, case_insensitive: bool
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _tokenize(text: str, *, case_insensitive: bool) -> list[str]:
    if case_insensitive:
        text = text.lower()
    return TOKEN_PATTERN.findall(text)


# [함수 설명]
# - 목적: _extract_title 처리 로직을 수행한다.
# - 입력: path: Path, text: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _extract_title(path: Path, text: str) -> str:
    if path.suffix.lower() == ".md":
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title
    return path.name


# [함수 설명]
# - 목적: _chunk_text 처리 로직을 수행한다.
# - 입력: extension: str, text: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _chunk_text(extension: str, text: str) -> list[str]:
    if extension == ".md":
        return _chunk_markdown(text)
    return _chunk_plaintext(text)


# [함수 설명]
# - 목적: _chunk_markdown 처리 로직을 수행한다.
# - 입력: text: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: _chunk_plaintext 처리 로직을 수행한다.
# - 입력: text: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
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


# [함수 설명]
# - 목적: _normalize_term 처리 로직을 수행한다.
# - 입력: term: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _normalize_term(term: str) -> str:
    normalized = term.strip().lower()
    return normalized


# [함수 설명]
# - 목적: _sorted_unique 처리 로직을 수행한다.
# - 입력: items: list[str]
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _sorted_unique(items: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return sorted(deduped)

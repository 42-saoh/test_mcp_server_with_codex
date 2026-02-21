# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from pathlib import Path

from fastapi.testclient import TestClient

import app.api.mcp as mcp_api
from app.main import app


def _stub_standardization_spec(name: str, obj_type: str) -> dict[str, object]:
    spec_payload = mcp_api._empty_spec_payload()
    spec_payload["tags"] = ["dynamic_sql", "cursor", "uses_transaction"]
    spec_payload["templates"] = [
        {"id": "TPL_DYNAMIC_SQL", "source": "business_rules", "confidence": 0.9}
    ]
    spec_payload["risks"] = {
        "migration_impacts": ["IMP_DYN_SQL"],
        "performance": ["RISK_SELECT_STAR"],
        "db_dependency": [],
    }
    return {
        "version": "5.1.0",
        "object": {
            "name": name,
            "type": obj_type,
            "normalized": name.lower(),
        },
        "spec": spec_payload,
        "errors": [],
    }


def _create_docs(docs_dir: Path) -> None:
    docs_dir.mkdir()
    (docs_dir / "dynamic_sql.md").write_text(
        "# Dynamic SQL in MyBatis\n\n"
        "Prefer dynamic sql sections with <if>, <choose>, and <foreach>.\n"
        "Avoid string concatenation for predicates.\n",
        encoding="utf-8",
    )
    (docs_dir / "cursor_replacement.md").write_text(
        "# Replacing Cursor Logic\n\n"
        "Replace cursor loops with set based statements and batched operations.\n",
        encoding="utf-8",
    )
    (docs_dir / "transaction_boundary.md").write_text(
        "# Service-layer Transactions\n\n"
        "Move transaction boundary controls to @Transactional service methods.\n",
        encoding="utf-8",
    )


def test_standardize_spec_with_evidence_returns_documents_when_docs_exist(
    tmp_path, monkeypatch
) -> None:
    docs_dir = tmp_path / "docs"
    _create_docs(docs_dir)
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(name, obj_type),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "-- synthetic",
            "options": {"docs_dir": str(docs_dir), "top_k": 3, "max_snippet_chars": 120},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    evidence = payload["evidence"]
    errors = payload["errors"]

    assert evidence["query_terms"]
    assert len(evidence["documents"]) >= 1
    assert all(len(doc["snippet"]) <= 120 for doc in evidence["documents"])
    assert len(evidence["pattern_recommendations"]) >= 1
    assert all(
        code not in " ".join(errors)
        for code in ["DOCS_EMPTY", "DOCS_DIR_NOT_FOUND", "QUERY_TERMS_EMPTY"]
    )


def test_standardize_spec_with_evidence_missing_docs_dir(tmp_path, monkeypatch) -> None:
    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(name, obj_type),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "-- synthetic",
            "options": {"docs_dir": str(missing_dir)},
        },
    )

    assert response.status_code == 200
    assert "DOCS_DIR_NOT_FOUND" in " ".join(response.json()["errors"])


def test_standardize_spec_with_evidence_empty_docs_dir(tmp_path, monkeypatch) -> None:
    docs_dir = tmp_path / "empty_docs"
    docs_dir.mkdir()
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(name, obj_type),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "-- synthetic",
            "options": {"docs_dir": str(docs_dir)},
        },
    )

    assert response.status_code == 200
    assert "DOCS_EMPTY" in " ".join(response.json()["errors"])


def test_standardize_spec_with_evidence_snippet_truncation_error(tmp_path, monkeypatch) -> None:
    docs_dir = tmp_path / "docs"
    _create_docs(docs_dir)
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(name, obj_type),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "-- synthetic",
            "options": {"docs_dir": str(docs_dir), "top_k": 3, "max_snippet_chars": 20},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any("SNIPPET_TRUNCATED" in error for error in payload["errors"])
    assert payload["evidence"]["documents"]


def test_standardize_spec_with_evidence_default_docs_dir_uses_standards(monkeypatch) -> None:
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(name, obj_type),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "-- synthetic",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["documents"]
    assert not any("DOCS_DIR_NOT_FOUND" in error for error in payload["errors"])

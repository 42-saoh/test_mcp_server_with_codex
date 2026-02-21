# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import app.api.mcp as mcp_api
from app.main import app

FIXTURE_SPECS = {
    "dynamic_sql": {
        "tags": ["dynamic_sql", "uses_transaction"],
        "templates": [
            {"id": "TPL_VALIDATE_REQUIRED_PARAM", "source": "business_rules", "confidence": 0.9}
        ],
        "risks": {"migration_impacts": ["IMP_DYN_SQL"], "performance": [], "db_dependency": []},
    },
    "cursor": {
        "tags": ["cursor", "uses_transaction"],
        "templates": [],
        "risks": {"migration_impacts": ["IMP_CURSOR"], "performance": [], "db_dependency": []},
    },
    "transaction": {
        "tags": ["uses_transaction", "has_writes"],
        "templates": [
            {"id": "TPL_ERROR_TO_EXCEPTION", "source": "business_rules", "confidence": 0.8}
        ],
        "risks": {"migration_impacts": [], "performance": [], "db_dependency": []},
    },
    "external_dep": {
        "tags": ["linked_server", "cross_db"],
        "templates": [],
        "risks": {
            "migration_impacts": ["IMP_LINKED_SERVER"],
            "performance": [],
            "db_dependency": ["RSN_LINKED_SERVER", "RSN_CROSS_DB"],
        },
    },
    "perf_select_star": {
        "tags": ["perf_risk_high"],
        "templates": [],
        "risks": {"migration_impacts": [], "performance": ["PRF_SELECT_STAR"], "db_dependency": []},
    },
}


def _stub_standardization_spec(
    name: str, obj_type: str, sql: str | None = None
) -> dict[str, object]:
    spec_payload = mcp_api._empty_spec_payload()
    fixture = FIXTURE_SPECS.get((sql or "").strip(), FIXTURE_SPECS["dynamic_sql"])
    spec_payload["tags"] = fixture["tags"]
    spec_payload["templates"] = fixture["templates"]
    spec_payload["risks"] = fixture["risks"]
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
    (docs_dir / "patterns.md").write_text(
        "# Pattern Index\n\n"
        "PAT_MYBATIS_DYNAMIC_TAGS dynamic sql mybatis if choose foreach\n"
        "PAT_REPLACE_CURSOR_SET_BASED cursor set based\n"
        "PAT_SERVICE_LAYER_TX transaction service boundary transactional\n"
        "PAT_ISOLATE_EXTERNAL_INTEGRATION linked server cross database integration external\n"
        "PAT_AVOID_SELECT_STAR select columns explicit\n",
        encoding="utf-8",
    )
    (docs_dir / "identifiers.md").write_text(
        "# Identifier Index\n\n"
        "IMP_DYN_SQL IMP_CURSOR IMP_LINKED_SERVER RSN_LINKED_SERVER RSN_CROSS_DB PRF_SELECT_STAR\n"
        "TPL_VALIDATE_REQUIRED_PARAM TPL_ERROR_TO_EXCEPTION uses_transaction dynamic_sql cursor linked_server cross_db\n",
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
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "dynamic_sql",
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


@pytest.mark.parametrize(
    "fixture_name,expect_patterns",
    [
        ("dynamic_sql", True),
        ("cursor", True),
        ("transaction", True),
        ("external_dep", True),
        ("perf_select_star", True),
    ],
)
def test_standardize_spec_with_evidence_fixture_reliability(
    tmp_path, monkeypatch, fixture_name: str, expect_patterns: bool
) -> None:
    docs_dir = tmp_path / "docs"
    _create_docs(docs_dir)
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Fixture", "type": "procedure"},
            "sql": fixture_name,
            "options": {"docs_dir": str(docs_dir), "top_k": 3, "max_snippet_chars": 90},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    errors_joined = " ".join(payload["errors"])
    evidence = payload["evidence"]

    assert "DOCS_DIR_NOT_FOUND" not in errors_joined
    assert "DOCS_EMPTY" not in errors_joined
    assert evidence["query_terms"]
    assert evidence["documents"]
    assert all(doc["snippet"] and len(doc["snippet"]) <= 90 for doc in evidence["documents"])

    if expect_patterns:
        assert evidence["pattern_recommendations"]
        assert any(
            recommendation.get("source_doc_id")
            for recommendation in evidence["pattern_recommendations"]
        )


def test_standardize_spec_with_evidence_missing_docs_dir(tmp_path, monkeypatch) -> None:
    missing_dir = tmp_path / "missing"
    monkeypatch.setattr(
        mcp_api,
        "build_standardization_spec",
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "dynamic_sql",
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
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "dynamic_sql",
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
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "dynamic_sql",
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
        lambda name, obj_type, sql, inputs, options: _stub_standardization_spec(
            name, obj_type, sql
        ),
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Smoke", "type": "procedure"},
            "sql": "dynamic_sql",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["documents"]
    assert not any("DOCS_DIR_NOT_FOUND" in error for error in payload["errors"])

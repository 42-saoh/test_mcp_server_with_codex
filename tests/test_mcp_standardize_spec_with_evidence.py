# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: standardize spec with evidence retrieval 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_with_evidence_retrieval(tmp_path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "mybatis_dynamic_sql.md").write_text(
        "# MyBatis Dynamic SQL Standard\n\n"
        "Prefer dynamic_sql handling with <if>/<choose>/<foreach> tags to avoid concatenation.\n"
        "Use mybatis tags to keep SQL readable.\n",
        encoding="utf-8",
    )
    (docs_dir / "transactions.md").write_text(
        "# Transaction Boundaries\n\n"
        "Define @Transactional at the service layer and keep boundaries consistent.\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Sample", "type": "procedure"},
            "sql": """
            CREATE PROCEDURE dbo.usp_Sample AS
            BEGIN
                BEGIN TRANSACTION;
                DECLARE @dyn NVARCHAR(100) = 'SENTINEL SELECT 1';
                EXEC(@dyn);
                COMMIT TRANSACTION;
            END
            """,
            "options": {
                "docs_dir": str(docs_dir),
                "top_k": 5,
                "max_snippet_chars": 120,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()

    documents = payload["evidence"]["documents"]
    assert len(documents) <= 5
    assert any("mybatis_dynamic_sql.md" in doc["source"] for doc in documents)
    assert all(len(doc["snippet"]) <= 120 for doc in documents)
    assert "PAT_MYBATIS_DYNAMIC_TAGS" in {
        item["id"] for item in payload["evidence"]["pattern_recommendations"]
    }
    assert "SENTINEL" not in str(payload)


# [함수 설명]
# - 목적: standardize spec with evidence missing docs dir 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_with_evidence_missing_docs_dir(tmp_path) -> None:
    missing_dir = tmp_path / "missing"
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_Sample", "type": "procedure"},
            "sql": "CREATE PROCEDURE dbo.usp_Sample AS EXEC('SELECT 1');",
            "options": {"docs_dir": str(missing_dir)},
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["evidence"]["documents"] == []
    assert "DOCS_DIR_NOT_FOUND" in " ".join(payload["errors"])
    assert "PAT_MYBATIS_DYNAMIC_TAGS" in {
        item["id"] for item in payload["evidence"]["pattern_recommendations"]
    }


# [함수 설명]
# - 목적: standardize spec with evidence determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_with_evidence_determinism(tmp_path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "mybatis_dynamic_sql.md").write_text(
        "# MyBatis Dynamic SQL Standard\n\n"
        "Prefer dynamic_sql handling with <if>/<choose>/<foreach> tags.\n",
        encoding="utf-8",
    )
    (docs_dir / "transactions.md").write_text(
        "# Transaction Boundaries\n\nDefine @Transactional at the service layer.\n",
        encoding="utf-8",
    )

    client = TestClient(app)
    request_payload = {
        "object": {"name": "dbo.usp_Sample", "type": "procedure"},
        "sql": "CREATE PROCEDURE dbo.usp_Sample AS EXEC('SELECT 1');",
        "options": {"docs_dir": str(docs_dir), "top_k": 3},
    }

    response_first = client.post("/mcp/standardize/spec-with-evidence", json=request_payload)
    response_second = client.post("/mcp/standardize/spec-with-evidence", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    first_payload = response_first.json()
    second_payload = response_second.json()
    assert first_payload["evidence"]["documents"] == second_payload["evidence"]["documents"]
    assert (
        first_payload["evidence"]["pattern_recommendations"]
        == second_payload["evidence"]["pattern_recommendations"]
    )

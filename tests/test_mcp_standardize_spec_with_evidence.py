from fastapi.testclient import TestClient

from app.main import app


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

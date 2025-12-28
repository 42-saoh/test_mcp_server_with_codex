from fastapi.testclient import TestClient

from app.main import app


def test_standardize_spec_minimal_read_only() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_ReadOnly", "type": "procedure"},
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT id FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    tags = payload["spec"]["tags"]
    assert "read_only" in tags
    assert "no_txn" in tags

    dependencies = payload["spec"]["dependencies"]
    table_names = {item.lower() for item in dependencies["tables"]}
    assert "dbo.users" in table_names

    one_liner = payload["spec"]["summary"]["one_liner"].upper()
    assert "FROM DBO." not in one_liner
    assert "SELECT" not in one_liner


def test_standardize_spec_complex_signals() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_Complex", "type": "procedure"},
            "sql": """
            CREATE PROCEDURE dbo.usp_Complex AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                COMMIT TRAN;
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    tags = payload["spec"]["tags"]
    assert "dynamic_sql" in tags
    assert "uses_transaction" in tags
    assert "difficulty_high" in tags
    assert tags == sorted(tags)

    recommendations = payload["spec"]["recommendations"]
    recommendation_ids = [item["id"] for item in recommendations]
    assert recommendation_ids == sorted(recommendation_ids)

    templates = payload["spec"]["templates"]
    if templates:
        expected = sorted(templates, key=lambda item: (-item["confidence"], item["id"]))
        assert templates == expected


def test_standardize_spec_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_Commented", "type": "procedure"},
            "sql": """
            CREATE PROCEDURE dbo.usp_Commented AS
            BEGIN
                -- SELECT * FROM dbo.Users;
                DECLARE @note NVARCHAR(100) = 'SELECT * FROM dbo.Users';
                SELECT id FROM dbo.Users;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    recommendation_ids = {item["id"] for item in payload["spec"]["recommendations"]}
    assert "REC_AVOID_SELECT_STAR" not in recommendation_ids


def test_standardize_spec_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "object": {"name": "dbo.usp_Same", "type": "procedure"},
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
    }

    response_first = client.post("/mcp/standardize/spec", json=request_payload)
    response_second = client.post("/mcp/standardize/spec", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

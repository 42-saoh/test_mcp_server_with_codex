from fastapi.testclient import TestClient

from app.main import app


def test_mybatis_difficulty_simple_select() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] == "low"
    assert summary["is_rewrite_recommended"] is True
    assert summary["confidence"] >= 0.8


def test_mybatis_difficulty_dynamic_cursor_temp_txn_complex() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_DynamicCursor",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_DynamicCursor AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                CREATE TABLE #tmp(id INT);
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                COMMIT TRAN;
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] in {"high", "very_high"}
    assert summary["is_rewrite_recommended"] is False

    factor_ids = {item["id"] for item in payload["factors"]}
    assert "FAC_DYN_SQL" in factor_ids
    assert "FAC_CURSOR" in factor_ids

    recommendation_ids = {item["id"] for item in payload["recommendations"]}
    assert "REC_CALL_SP_FIRST" in recommendation_ids


def test_mybatis_difficulty_moderate_writes() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_WriteModerate",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_WriteModerate AS
            BEGIN
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                UPDATE dbo.Users SET name = 'x' WHERE id = 1;
                DELETE FROM dbo.UserFlags WHERE user_id = 1;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] == "medium"
    assert summary["is_rewrite_recommended"] is True


def test_mybatis_difficulty_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
    }

    response_first = client.post("/mcp/migration/mybatis-difficulty", json=request_payload)
    response_second = client.post("/mcp/migration/mybatis-difficulty", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

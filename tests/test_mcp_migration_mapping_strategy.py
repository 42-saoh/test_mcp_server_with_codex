from fastapi.testclient import TestClient

from app.main import app


def test_mapping_strategy_read_only_low_complexity() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["approach"] == "rewrite_to_mybatis_sql"
    assert summary["difficulty"] == "low"
    assert summary["confidence"] >= 0.8

    skeleton = payload["mybatis"]["xml_template"]["skeleton"]
    assert "dbo.Users" not in skeleton
    assert "dbo." not in skeleton


def test_mapping_strategy_dynamic_cursor_temp_table() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_DynamicCursor",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_DynamicCursor AS
            BEGIN
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                CREATE TABLE #tmp(id INT);
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["approach"] == "call_sp_first"
    assert summary["difficulty"] in {"high", "very_high"}

    anti_pattern_ids = {item["id"] for item in payload["strategy"]["anti_patterns"]}
    assert "ANTI_DYN_SQL_CONCAT" in anti_pattern_ids


def test_mapping_strategy_writes_with_transaction() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_WriteTxn",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_WriteTxn AS
            BEGIN
                BEGIN TRAN;
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                COMMIT TRAN;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["difficulty"] in {"medium", "high", "very_high"}
    recommendation_ids = {item["id"] for item in payload["recommendations"]}
    assert "REC_SERVICE_TXN_AWARE" in recommendation_ids


def test_mapping_strategy_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_items": 10},
    }

    response_first = client.post("/mcp/migration/mapping-strategy", json=request_payload)
    response_second = client.post("/mcp/migration/mapping-strategy", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

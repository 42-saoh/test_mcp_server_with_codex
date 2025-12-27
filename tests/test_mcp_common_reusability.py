from fastapi.testclient import TestClient

from app.main import app


def test_reusability_read_only_lookup() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/reusability",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["score"] >= 80
    assert summary["grade"] in {"A", "B"}
    assert summary["is_candidate"] is True
    assert summary["candidate_type"] == "lookup"

    signals = payload["signals"]
    assert signals["read_only"] is True
    assert signals["has_writes"] is False


def test_reusability_dynamic_cursor_transaction_writes() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/reusability",
        json={
            "name": "dbo.usp_Bad",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Bad AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                EXEC sp_executesql N'SELECT 1';
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                COMMIT TRAN;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["score"] < 50
    assert summary["grade"] == "D"
    assert summary["is_candidate"] is False

    reason_ids = {reason["id"] for reason in payload["reasons"]}
    assert "RSN_DYN_SQL" in reason_ids
    assert "RSN_CURSOR" in reason_ids
    assert "RSN_TXN" in reason_ids
    assert "RSN_WRITES" in reason_ids


def test_reusability_determinism() -> None:
    client = TestClient(app)

    payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_reason_items": 10},
    }

    response_first = client.post("/mcp/common/reusability", json=payload)
    response_second = client.post("/mcp/common/reusability", json=payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

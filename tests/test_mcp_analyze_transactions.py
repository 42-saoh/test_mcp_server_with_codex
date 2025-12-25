from fastapi.testclient import TestClient

from app.main import app


def test_mcp_analyze_transactions_absent() -> None:
    client = TestClient(app)
    payload = {
        "sql": "SELECT 1",
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    transactions = data["transactions"]
    assert transactions["uses_transaction"] is False
    assert transactions["begin_count"] == 0
    assert transactions["commit_count"] == 0
    assert transactions["rollback_count"] == 0
    assert transactions["savepoint_count"] == 0
    assert transactions["has_try_catch"] is False
    assert transactions["xact_abort"] is None
    assert transactions["isolation_level"] is None


def test_mcp_analyze_transactions_present() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        SET XACT_ABORT ON;
        SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
        BEGIN TRY
            BEGIN TRAN
            SELECT @@TRANCOUNT;
            COMMIT TRANSACTION;
        END TRY
        BEGIN CATCH
            IF XACT_STATE() <> 0
                ROLLBACK TRAN;
            THROW;
        END CATCH
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    transactions = data["transactions"]
    assert transactions["uses_transaction"] is True
    assert transactions["begin_count"] == 1
    assert transactions["commit_count"] == 1
    assert transactions["rollback_count"] == 1
    assert transactions["savepoint_count"] == 0
    assert transactions["has_try_catch"] is True
    assert transactions["xact_abort"] == "ON"
    assert transactions["isolation_level"] == "READ COMMITTED"
    assert "BEGIN TRAN" in transactions["signals"]
    assert "COMMIT" in transactions["signals"]
    assert "ROLLBACK" in transactions["signals"]
    assert "TRY/CATCH" in transactions["signals"]
    assert "XACT_ABORT ON" in transactions["signals"]
    assert "ISOLATION LEVEL READ COMMITTED" in transactions["signals"]
    assert "@@TRANCOUNT" in transactions["signals"]
    assert "XACT_STATE()" in transactions["signals"]
    assert "THROW" in transactions["signals"]

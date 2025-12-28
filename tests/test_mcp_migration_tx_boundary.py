from fastapi.testclient import TestClient

from app.main import app


def test_tx_boundary_read_only() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "none"
    assert summary["transactional"] is False
    assert summary["propagation"] == "SUPPORTS"
    assert summary["read_only"] is True
    assert summary["confidence"] >= 0.8


def test_tx_boundary_writes_service_layer() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_Write",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Write AS INSERT INTO dbo.AuditLog(id) VALUES (1);",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "service_layer"
    assert summary["transactional"] is True
    assert summary["propagation"] == "REQUIRED"


def test_tx_boundary_hybrid_with_transaction_signals() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_TxManaged",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_TxManaged AS
            BEGIN
                SET XACT_ABORT ON;
                SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
                BEGIN TRY
                    BEGIN TRAN;
                    INSERT INTO dbo.AuditLog(id) VALUES (1);
                    COMMIT TRAN;
                END TRY
                BEGIN CATCH
                    ROLLBACK TRAN;
                    THROW;
                END CATCH
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "hybrid"
    assert summary["isolation_level"]

    suggestion_ids = {item["id"] for item in payload["suggestions"]}
    assert "SUG_AVOID_DOUBLE_TX" in suggestion_ids
    assert "SUG_USE_NOT_SUPPORTED" in suggestion_ids


def test_tx_boundary_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_items": 10},
    }

    response_first = client.post(
        "/mcp/migration/transaction-boundary",
        json=request_payload,
    )
    response_second = client.post(
        "/mcp/migration/transaction-boundary",
        json=request_payload,
    )

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

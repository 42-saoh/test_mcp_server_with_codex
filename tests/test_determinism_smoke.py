from fastapi.testclient import TestClient

from app.main import app


def test_determinism_smoke_endpoints() -> None:
    client = TestClient(app)

    analyze_payload = {
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic AS
        BEGIN
            BEGIN TRAN;
            SELECT id FROM dbo.Users;
            UPDATE dbo.Users SET name = 'x' WHERE id = 1;
            COMMIT TRAN;
        END
        """,
        "dialect": "tsql",
    }

    first = client.post("/mcp/analyze", json=analyze_payload)
    second = client.post("/mcp/analyze", json=analyze_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    mapping_payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": analyze_payload["sql"],
    }

    first = client.post("/mcp/migration/mapping-strategy", json=mapping_payload)
    second = client.post("/mcp/migration/mapping-strategy", json=mapping_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    perf_payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": analyze_payload["sql"],
    }

    first = client.post("/mcp/quality/performance-risk", json=perf_payload)
    second = client.post("/mcp/quality/performance-risk", json=perf_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

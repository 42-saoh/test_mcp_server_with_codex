from fastapi.testclient import TestClient

from app.main import app


def test_mcp_analyze_extracts_tables_and_functions() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        CREATE PROCEDURE dbo.GetUserSummary AS
        BEGIN
            SELECT dbo.FormatName(u.FirstName, u.LastName) AS DisplayName,
                   COUNT(*) AS Total
            FROM dbo.Users u
            JOIN sales.Orders o ON o.UserId = u.Id
            WHERE u.IsActive = 1 AND YEAR(o.CreatedAt) = 2024
        END
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["version"] == "0.1"
    assert data["errors"] == []
    assert set(data["references"]["tables"]) >= {"DBO.USERS", "SALES.ORDERS"}
    assert set(data["references"]["functions"]) >= {"COUNT", "YEAR", "FORMATNAME"}

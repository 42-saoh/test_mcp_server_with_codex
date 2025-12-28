from fastapi.testclient import TestClient

from app.main import app


def _post(payload: dict) -> dict:
    client = TestClient(app)
    response = client.post("/mcp/quality/performance-risk", json=payload)
    assert response.status_code == 200
    return response.json()


def test_mcp_quality_performance_risk_low() -> None:
    payload = {
        "name": "dbo.usp_ReadOnly",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_ReadOnly
        AS
        SELECT col1, col2
        FROM dbo.Accounts
        WHERE col1 = 1;
        """,
        "options": {"dialect": "tsql"},
    }

    data = _post(payload)

    assert data["summary"]["risk_level"] == "low"
    assert data["summary"]["risk_score"] <= 24
    severities = {finding["severity"] for finding in data["findings"]}
    assert "critical" not in severities
    assert "high" not in severities


def test_mcp_quality_performance_risk_bad_patterns() -> None:
    payload = {
        "name": "dbo.usp_Bad",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Bad
        AS
        SELECT *
        FROM dbo.Customers WITH (NOLOCK)
        WHERE UPPER(name) LIKE '%x';
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert {
        "PRF_SELECT_STAR",
        "PRF_LEADING_WILDCARD_LIKE",
        "PRF_FUNCTION_ON_COLUMN",
        "PRF_NOLOCK",
    }.issubset(finding_ids)
    assert data["summary"]["risk_level"] in {"medium", "high", "critical"}


def test_mcp_quality_performance_risk_cursor_and_dynamic_sql() -> None:
    payload = {
        "name": "dbo.usp_Cursor",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Cursor
        AS
        DECLARE cur CURSOR FOR SELECT id FROM dbo.Items;
        OPEN cur;
        WHILE 1 = 1
        BEGIN
            EXEC(@sql);
            UPDATE dbo.Items SET name = name;
            FETCH NEXT FROM cur;
        END
        CLOSE cur;
        DEALLOCATE cur;
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert "PRF_CURSOR_RBAR" in finding_ids
    assert "PRF_DYNAMIC_SQL" in finding_ids
    assert "PRF_LOOP_RBAR" in finding_ids
    assert data["summary"]["risk_level"] in {"high", "critical"}


def test_mcp_quality_performance_risk_ignores_comments_and_strings() -> None:
    payload = {
        "name": "dbo.usp_Comments",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Comments
        AS
        -- SELECT * FROM dbo.Hidden WITH (NOLOCK)
        /* NOLOCK should not count */
        SELECT col1, 'SELECT * NOLOCK' AS note
        FROM dbo.Visible;
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert "PRF_SELECT_STAR" not in finding_ids
    assert "PRF_NOLOCK" not in finding_ids


def test_mcp_quality_performance_risk_determinism() -> None:
    payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic
        AS
        SELECT *
        FROM dbo.Orders
        WHERE amount IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20);
        """,
    }

    first = _post(payload)
    second = _post(payload)

    assert first == second

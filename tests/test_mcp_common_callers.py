from fastapi.testclient import TestClient

from app.main import app


def test_callers_no_matches() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.usp_T",
            "target_type": "procedure",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS SELECT 1;",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "has_callers": False,
        "caller_count": 0,
        "total_calls": 0,
    }
    assert payload["callers"] == []


def test_callers_multiple_exec_forms() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.usp_T",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC dbo.usp_T;
                        EXECUTE dbo.usp_T @p = 1;
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_B AS
                    BEGIN
                        -- EXEC dbo.usp_T
                        SELECT 'EXEC dbo.usp_T';
                    END
                    """,
                },
                {
                    "name": "dbo.usp_C",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_C AS
                    BEGIN
                        EXEC dbo.usp_T @p = 2;
                    END
                    """,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["caller_count"] == 2
    assert payload["summary"]["total_calls"] == 3
    assert payload["summary"]["has_callers"] is True

    callers = payload["callers"]
    assert callers[0]["name"] == "dbo.usp_A"
    assert callers[0]["call_count"] == 2
    assert "exec" in callers[0]["call_kinds"]
    assert "execute" in callers[0]["call_kinds"]
    assert "EXEC" in callers[0]["signals"]
    assert "EXECUTE" in callers[0]["signals"]

    assert callers[1]["name"] == "dbo.usp_C"
    assert callers[1]["call_count"] == 1


def test_callers_function_target() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.fn_T",
            "target_type": "function",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        SELECT dbo.fn_T(@x);
                    END
                    """,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_callers"] is True
    assert payload["summary"]["caller_count"] == 1
    assert payload["summary"]["total_calls"] == 1
    assert payload["callers"][0]["call_kinds"] == ["function_call"]

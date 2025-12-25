from fastapi.testclient import TestClient

from app.main import app


def test_mcp_analyze_control_flow_simple() -> None:
    client = TestClient(app)
    payload = {
        "sql": "SELECT 1",
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    control_flow = data["control_flow"]
    summary = control_flow["summary"]
    assert summary["has_branching"] is False
    assert summary["has_loops"] is False
    assert summary["has_try_catch"] is False
    assert summary["has_return"] is False
    assert summary["branch_count"] == 0
    assert summary["loop_count"] == 0
    assert summary["cyclomatic_complexity"] == 1
    node_types = {node["type"] for node in control_flow["graph"]["nodes"]}
    assert "start" in node_types
    assert "end" in node_types


def test_mcp_analyze_control_flow_complex() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        IF @flag = 1
        BEGIN
            SELECT 1;
        END
        ELSE
        BEGIN
            SELECT 2;
        END
        WHILE @i < 10
        BEGIN
            SET @i = @i + 1;
        END
        BEGIN TRY
            RETURN;
        END TRY
        BEGIN CATCH
            RETURN;
        END CATCH
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    control_flow = data["control_flow"]
    summary = control_flow["summary"]
    assert summary["has_branching"] is True
    assert summary["has_loops"] is True
    assert summary["has_try_catch"] is True
    assert summary["has_return"] is True
    assert summary["branch_count"] == 1
    assert summary["loop_count"] == 1
    assert summary["return_count"] >= 1
    expected_complexity = (
        1
        + summary["branch_count"]
        + summary["loop_count"]
        + (1 if summary["has_try_catch"] else 0)
        + (1 if summary["goto_count"] > 0 else 0)
    )
    assert summary["cyclomatic_complexity"] == expected_complexity
    node_types = {node["type"] for node in control_flow["graph"]["nodes"]}
    assert {"start", "if", "while", "try", "catch", "end"}.issubset(node_types)

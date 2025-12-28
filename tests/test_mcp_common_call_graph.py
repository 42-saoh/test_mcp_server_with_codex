from fastapi.testclient import TestClient

from app.main import app


def test_call_graph_simple_corpus() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS EXEC dbo.usp_B;",
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT dbo.fn_C(1);",
                },
                {
                    "name": "dbo.fn_C",
                    "type": "function",
                    "sql": "CREATE FUNCTION dbo.fn_C() RETURNS INT AS BEGIN RETURN 1; END",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["object_count"] == 3
    assert payload["summary"]["node_count"] == 3
    assert payload["summary"]["edge_count"] == 2

    assert payload["graph"]["nodes"] == [
        {"id": "dbo.fn_c", "name": "dbo.fn_C", "type": "function"},
        {"id": "dbo.usp_a", "name": "dbo.usp_A", "type": "procedure"},
        {"id": "dbo.usp_b", "name": "dbo.usp_B", "type": "procedure"},
    ]
    assert payload["graph"]["edges"] == [
        {
            "from": "dbo.usp_a",
            "to": "dbo.usp_b",
            "kind": "exec",
            "count": 1,
            "signals": ["EXEC"],
        },
        {
            "from": "dbo.usp_b",
            "to": "dbo.fn_c",
            "kind": "function_call",
            "count": 1,
            "signals": ["FUNCTION"],
        },
    ]


def test_call_graph_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC dbo.usp_B;
                        -- EXEC dbo.usp_B
                        SELECT 'EXEC dbo.usp_B';
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT 1;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 1
    assert payload["graph"]["edges"][0]["count"] == 1


def test_call_graph_ignores_dynamic_exec() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC(@sql);
                        EXEC sp_executesql @sql;
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT 1;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 0
    assert payload["graph"]["edges"] == []


def test_call_graph_ambiguous_target() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS EXEC usp_X;",
                },
                {
                    "name": "dbo.usp_X",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_X AS SELECT 1;",
                },
                {
                    "name": "alt.usp_X",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE alt.usp_X AS SELECT 2;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 0
    assert payload["errors"] == [
        {
            "id": "AMBIGUOUS_TARGET",
            "message": "Call to usp_x is ambiguous across schemas.",
            "object": "dbo.usp_A",
        }
    ]

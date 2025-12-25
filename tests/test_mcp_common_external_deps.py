from fastapi.testclient import TestClient

from app.main import app


def test_external_deps_none() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Simple",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Simple AS SELECT * FROM dbo.TableA;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"] == {
        "has_external_deps": False,
        "linked_server_count": 0,
        "cross_db_count": 0,
        "remote_exec_count": 0,
        "openquery_count": 0,
        "opendatasource_count": 0,
    }
    assert payload["external_dependencies"] == {
        "linked_servers": [],
        "cross_database": [],
        "remote_exec": [],
        "openquery": [],
        "opendatasource": [],
        "others": [],
    }


def test_external_deps_multiple_patterns() -> None:
    client = TestClient(app)

    sql = """
    CREATE PROCEDURE dbo.usp_Sample AS
    BEGIN
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
    END
    """

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Sample",
            "type": "procedure",
            "sql": sql,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_external_deps"] is True
    assert payload["summary"]["linked_server_count"] == 1
    assert payload["summary"]["cross_db_count"] == 1
    assert payload["summary"]["remote_exec_count"] == 1
    assert payload["summary"]["openquery_count"] == 1
    assert payload["summary"]["opendatasource_count"] == 0

    linked_servers = payload["external_dependencies"]["linked_servers"]
    assert linked_servers[0]["name"] == "LSRV1"
    assert set(linked_servers[0]["signals"]) == {"EXEC AT", "OPENQUERY", "four_part_name"}

    cross_database = payload["external_dependencies"]["cross_database"]
    assert cross_database == [
        {
            "database": "OtherDb",
            "schema": "dbo",
            "object": "TableY",
            "kind": "three_part_name",
        }
    ]

    remote_exec = payload["external_dependencies"]["remote_exec"]
    assert remote_exec == [{"target": "LSRV1", "kind": "exec_at", "signals": ["EXEC AT"]}]

    openquery = payload["external_dependencies"]["openquery"]
    assert openquery == [{"target": "LSRV1", "kind": "openquery", "signals": ["OPENQUERY"]}]


def test_external_deps_ignore_comments_and_strings() -> None:
    client = TestClient(app)

    sql = """
    CREATE PROCEDURE dbo.usp_Ignore AS
    BEGIN
        -- SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT 'LSRV1.OtherDb.dbo.TableX' AS Example;
    END
    """

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Ignore",
            "type": "procedure",
            "sql": sql,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_external_deps"] is False
    assert payload["summary"]["linked_server_count"] == 0
    assert payload["summary"]["cross_db_count"] == 0
    assert payload["summary"]["remote_exec_count"] == 0
    assert payload["summary"]["openquery_count"] == 0
    assert payload["summary"]["opendatasource_count"] == 0

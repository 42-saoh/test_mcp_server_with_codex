from fastapi.testclient import TestClient

from app.main import app


def _post(payload: dict) -> dict:
    client = TestClient(app)
    response = client.post("/mcp/quality/db-dependency", json=payload)
    assert response.status_code == 200
    return response.json()


def test_mcp_quality_db_dependency_low() -> None:
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
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] == "low"
    assert data["metrics"]["linked_server_count"] == 0
    assert data["metrics"]["cross_database_count"] == 0


def test_mcp_quality_db_dependency_cross_db_and_linked_server() -> None:
    payload = {
        "name": "dbo.usp_Dep",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Dep
        AS
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
        """,
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] in {"high", "critical"}
    assert data["metrics"]["linked_server_count"] == 1
    assert data["metrics"]["cross_database_count"] == 1
    assert data["metrics"]["openquery_count"] == 1
    assert data["metrics"]["remote_exec_count"] == 1

    linked_servers = {item["name"] for item in data["dependencies"]["linked_servers"]}
    assert "lsrv1" in linked_servers
    cross_db = {item["database"] for item in data["dependencies"]["cross_database"]}
    assert "otherdb" in cross_db


def test_mcp_quality_db_dependency_risky_system_and_clr() -> None:
    payload = {
        "name": "dbo.usp_Risky",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Risky
        AS
        EXEC xp_cmdshell 'dir';
        EXEC sp_OACreate 'scripting.filesystemobject', @obj OUT;
        CREATE ASSEMBLY MyAsm FROM 0x00 WITH PERMISSION_SET = EXTERNAL_ACCESS;
        """,
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] == "critical"
    reason_ids = {reason["id"] for reason in data["reasons"]}
    assert "RSN_XP_CMDSHELL" in reason_ids
    assert "RSN_CLR" in reason_ids


def test_mcp_quality_db_dependency_ignores_comments_and_strings() -> None:
    payload = {
        "name": "dbo.usp_Comments",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Comments
        AS
        -- SELECT * FROM LSRV1.OtherDb.dbo.TableX
        /* OPENQUERY(LSRV1, 'SELECT 1') */
        SELECT col1, 'LSRV1.OtherDb.dbo.TableX OPENQUERY(LSRV1, ...)' AS note
        FROM dbo.Visible;
        """,
    }

    data = _post(payload)

    assert data["metrics"]["linked_server_count"] == 0
    assert data["metrics"]["openquery_count"] == 0
    assert data["metrics"]["cross_database_count"] == 0


def test_mcp_quality_db_dependency_determinism() -> None:
    payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic
        AS
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
        """,
    }

    data = _post(payload)
    data_repeat = _post(payload)

    assert data == data_repeat

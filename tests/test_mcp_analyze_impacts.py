from fastapi.testclient import TestClient

from app.main import app


def test_mcp_analyze_impacts_clean_sql() -> None:
    client = TestClient(app)
    payload = {
        "sql": "SELECT 1",
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    impacts = data["migration_impacts"]
    assert impacts["has_impact"] is False
    assert impacts["items"] == []


def test_mcp_analyze_impacts_detects_patterns() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        DECLARE cur_users CURSOR FOR SELECT 1;
        OPEN cur_users;
        FETCH NEXT FROM cur_users;
        CLOSE cur_users;
        DEALLOCATE cur_users;
        CREATE TABLE #TempIds (Id INT);
        INSERT INTO #TempIds (Id) VALUES (1);
        DECLARE @sql NVARCHAR(MAX) = N'SELECT 1';
        EXEC sp_executesql @sql;
        SELECT SCOPE_IDENTITY();
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    impacts = data["migration_impacts"]
    assert impacts["has_impact"] is True

    items_by_id = {item["id"]: item for item in impacts["items"]}
    assert "IMP_DYN_SQL" in items_by_id
    assert "IMP_CURSOR" in items_by_id
    assert "IMP_TEMP_TABLE" in items_by_id
    assert "IMP_IDENTITY" in items_by_id

    assert items_by_id["IMP_DYN_SQL"]["severity"] == "high"
    assert items_by_id["IMP_DYN_SQL"]["category"] == "dynamic_sql"
    assert "sp_executesql" in items_by_id["IMP_DYN_SQL"]["signals"]

    assert items_by_id["IMP_CURSOR"]["severity"] == "high"
    assert items_by_id["IMP_CURSOR"]["category"] == "cursor"
    assert "DECLARE CURSOR" in items_by_id["IMP_CURSOR"]["signals"]

    assert items_by_id["IMP_TEMP_TABLE"]["severity"] == "medium"
    assert items_by_id["IMP_TEMP_TABLE"]["category"] == "temp_table"
    assert "TEMP_TABLE" in items_by_id["IMP_TEMP_TABLE"]["signals"]

    assert items_by_id["IMP_IDENTITY"]["severity"] == "medium"
    assert items_by_id["IMP_IDENTITY"]["category"] == "identity"
    assert "SCOPE_IDENTITY()" in items_by_id["IMP_IDENTITY"]["signals"]

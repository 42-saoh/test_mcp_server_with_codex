from fastapi.testclient import TestClient

from app.main import app
from app.services.tsql_analyzer import analyze_data_changes


def test_mcp_analyze_data_changes_read_only() -> None:
    client = TestClient(app)
    payload = {
        "sql": "SELECT 1",
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    data_changes = data["data_changes"]
    assert data_changes["has_writes"] is False
    for op in data_changes["operations"].values():
        assert op["count"] == 0
        assert op["tables"] == []
    assert data_changes["table_operations"] == []
    assert data_changes["signals"] == []
    assert data_changes["notes"] == []


def test_mcp_analyze_data_changes_mixed_dml() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        INSERT INTO dbo.A (Id) OUTPUT INSERTED.Id VALUES (1);
        UPDATE dbo.B SET Name = 'x';
        DELETE FROM dbo.C OUTPUT DELETED.Id WHERE Id = 1;
        MERGE INTO dbo.D AS target
        USING dbo.Source AS src ON target.Id = src.Id
        WHEN MATCHED THEN UPDATE SET target.Name = src.Name;
        TRUNCATE TABLE dbo.E;
        SELECT Id INTO dbo.F FROM dbo.G;
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    data_changes = data["data_changes"]
    assert data_changes["has_writes"] is True

    operations = data_changes["operations"]
    assert operations["insert"]["count"] == 1
    assert operations["update"]["count"] == 1
    assert operations["delete"]["count"] == 1
    assert operations["merge"]["count"] == 1
    assert operations["truncate"]["count"] == 1
    assert operations["select_into"]["count"] == 1
    assert "DBO.A" in operations["insert"]["tables"]
    assert "DBO.B" in operations["update"]["tables"]
    assert "DBO.C" in operations["delete"]["tables"]
    assert "DBO.D" in operations["merge"]["tables"]
    assert "DBO.E" in operations["truncate"]["tables"]
    assert "DBO.F" in operations["select_into"]["tables"]

    table_ops = {item["table"]: set(item["ops"]) for item in data_changes["table_operations"]}
    assert table_ops["DBO.A"] == {"insert"}
    assert table_ops["DBO.B"] == {"update"}
    assert table_ops["DBO.C"] == {"delete"}
    assert table_ops["DBO.D"] == {"merge"}
    assert table_ops["DBO.E"] == {"truncate"}
    assert table_ops["DBO.F"] == {"select_into"}

    signals = set(data_changes["signals"])
    assert {"INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE", "SELECT INTO"}.issubset(signals)
    assert {"OUTPUT", "INSERTED", "DELETED"}.issubset(signals)


def test_data_changes_fallback_regex() -> None:
    result = analyze_data_changes("UPDATE dbo.B SET", "tsql")
    data_changes = result["data_changes"]

    assert data_changes["has_writes"] is True
    assert data_changes["operations"]["update"]["count"] == 1
    assert data_changes["operations"]["update"]["tables"] == ["DBO.B"]

# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app
from app.services.tsql_analyzer import analyze_data_changes


# [함수 설명]
# - 목적: mcp analyze data changes read only 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
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


# [함수 설명]
# - 목적: mcp analyze data changes mixed dml 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
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


# [함수 설명]
# - 목적: data changes fallback regex 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_data_changes_fallback_regex() -> None:
    result = analyze_data_changes("UPDATE dbo.B SET", "tsql")
    data_changes = result["data_changes"]

    assert data_changes["has_writes"] is True
    assert data_changes["operations"]["update"]["count"] == 1
    assert data_changes["operations"]["update"]["tables"] == ["DBO.B"]

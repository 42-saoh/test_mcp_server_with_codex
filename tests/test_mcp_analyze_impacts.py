# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: mcp analyze impacts clean sql 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
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


# [함수 설명]
# - 목적: mcp analyze impacts detects patterns 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
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

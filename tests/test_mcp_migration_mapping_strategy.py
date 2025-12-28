# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: mapping strategy read only low complexity 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mapping_strategy_read_only_low_complexity() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["approach"] == "rewrite_to_mybatis_sql"
    assert summary["difficulty"] == "low"
    assert summary["confidence"] >= 0.8

    skeleton = payload["mybatis"]["xml_template"]["skeleton"]
    assert "dbo.Users" not in skeleton
    assert "dbo." not in skeleton


# [함수 설명]
# - 목적: mapping strategy dynamic cursor temp table 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mapping_strategy_dynamic_cursor_temp_table() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_DynamicCursor",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_DynamicCursor AS
            BEGIN
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                CREATE TABLE #tmp(id INT);
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["approach"] == "call_sp_first"
    assert summary["difficulty"] in {"high", "very_high"}

    anti_pattern_ids = {item["id"] for item in payload["strategy"]["anti_patterns"]}
    assert "ANTI_DYN_SQL_CONCAT" in anti_pattern_ids


# [함수 설명]
# - 목적: mapping strategy writes with transaction 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mapping_strategy_writes_with_transaction() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mapping-strategy",
        json={
            "name": "dbo.usp_WriteTxn",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_WriteTxn AS
            BEGIN
                BEGIN TRAN;
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                COMMIT TRAN;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["difficulty"] in {"medium", "high", "very_high"}
    recommendation_ids = {item["id"] for item in payload["recommendations"]}
    assert "REC_SERVICE_TXN_AWARE" in recommendation_ids


# [함수 설명]
# - 목적: mapping strategy determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mapping_strategy_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_items": 10},
    }

    response_first = client.post("/mcp/migration/mapping-strategy", json=request_payload)
    response_second = client.post("/mcp/migration/mapping-strategy", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

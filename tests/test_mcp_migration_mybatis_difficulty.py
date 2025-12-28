# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: mybatis difficulty simple select 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mybatis_difficulty_simple_select() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] == "low"
    assert summary["is_rewrite_recommended"] is True
    assert summary["confidence"] >= 0.8


# [함수 설명]
# - 목적: mybatis difficulty dynamic cursor temp txn complex 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mybatis_difficulty_dynamic_cursor_temp_txn_complex() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_DynamicCursor",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_DynamicCursor AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                CREATE TABLE #tmp(id INT);
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                IF EXISTS (SELECT 1 FROM dbo.Users) BEGIN SELECT 1; END
                COMMIT TRAN;
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] in {"high", "very_high"}
    assert summary["is_rewrite_recommended"] is False

    factor_ids = {item["id"] for item in payload["factors"]}
    assert "FAC_DYN_SQL" in factor_ids
    assert "FAC_CURSOR" in factor_ids

    recommendation_ids = {item["id"] for item in payload["recommendations"]}
    assert "REC_CALL_SP_FIRST" in recommendation_ids


# [함수 설명]
# - 목적: mybatis difficulty moderate writes 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mybatis_difficulty_moderate_writes() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/mybatis-difficulty",
        json={
            "name": "dbo.usp_WriteModerate",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_WriteModerate AS
            BEGIN
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                UPDATE dbo.Users SET name = 'x' WHERE id = 1;
                DELETE FROM dbo.UserFlags WHERE user_id = 1;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["difficulty_level"] == "medium"
    assert summary["is_rewrite_recommended"] is True


# [함수 설명]
# - 목적: mybatis difficulty determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mybatis_difficulty_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
    }

    response_first = client.post("/mcp/migration/mybatis-difficulty", json=request_payload)
    response_second = client.post("/mcp/migration/mybatis-difficulty", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: standardize spec minimal read only 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_minimal_read_only() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_ReadOnly", "type": "procedure"},
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT id FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    tags = payload["spec"]["tags"]
    assert "read_only" in tags
    assert "no_txn" in tags

    dependencies = payload["spec"]["dependencies"]
    table_names = {item.lower() for item in dependencies["tables"]}
    assert "dbo.users" in table_names

    one_liner = payload["spec"]["summary"]["one_liner"].upper()
    assert "FROM DBO." not in one_liner
    assert "SELECT" not in one_liner


# [함수 설명]
# - 목적: standardize spec complex signals 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_complex_signals() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_Complex", "type": "procedure"},
            "sql": """
            CREATE PROCEDURE dbo.usp_Complex AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                DECLARE @dyn NVARCHAR(100) = 'SELECT 1';
                EXEC(@dyn + ' FROM dbo.Users');
                COMMIT TRAN;
                CLOSE c;
                DEALLOCATE c;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    tags = payload["spec"]["tags"]
    assert "dynamic_sql" in tags
    assert "uses_transaction" in tags
    assert "difficulty_high" in tags
    assert tags == sorted(tags)

    recommendations = payload["spec"]["recommendations"]
    recommendation_ids = [item["id"] for item in recommendations]
    assert recommendation_ids == sorted(recommendation_ids)

    templates = payload["spec"]["templates"]
    if templates:
        expected = sorted(templates, key=lambda item: (-item["confidence"], item["id"]))
        assert templates == expected


# [함수 설명]
# - 목적: standardize spec ignores comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_Commented", "type": "procedure"},
            "sql": """
            CREATE PROCEDURE dbo.usp_Commented AS
            BEGIN
                -- SELECT * FROM dbo.Users;
                DECLARE @note NVARCHAR(100) = 'SELECT * FROM dbo.Users';
                SELECT id FROM dbo.Users;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    recommendation_ids = {item["id"] for item in payload["spec"]["recommendations"]}
    assert "REC_AVOID_SELECT_STAR" not in recommendation_ids


# [함수 설명]
# - 목적: standardize spec determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_standardize_spec_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "object": {"name": "dbo.usp_Same", "type": "procedure"},
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
    }

    response_first = client.post("/mcp/standardize/spec", json=request_payload)
    response_second = client.post("/mcp/standardize/spec", json=request_payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

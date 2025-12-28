# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: callers no matches 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_callers_no_matches() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.usp_T",
            "target_type": "procedure",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS SELECT 1;",
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"] == {
        "has_callers": False,
        "caller_count": 0,
        "total_calls": 0,
    }
    assert payload["callers"] == []


# [함수 설명]
# - 목적: callers multiple exec forms 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_callers_multiple_exec_forms() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.usp_T",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC dbo.usp_T;
                        EXECUTE dbo.usp_T @p = 1;
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_B AS
                    BEGIN
                        -- EXEC dbo.usp_T
                        SELECT 'EXEC dbo.usp_T';
                    END
                    """,
                },
                {
                    "name": "dbo.usp_C",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_C AS
                    BEGIN
                        EXEC dbo.usp_T @p = 2;
                    END
                    """,
                },
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["caller_count"] == 2
    assert payload["summary"]["total_calls"] == 3
    assert payload["summary"]["has_callers"] is True

    callers = payload["callers"]
    assert callers[0]["name"] == "dbo.usp_A"
    assert callers[0]["call_count"] == 2
    assert "exec" in callers[0]["call_kinds"]
    assert "execute" in callers[0]["call_kinds"]
    assert "EXEC" in callers[0]["signals"]
    assert "EXECUTE" in callers[0]["signals"]

    assert callers[1]["name"] == "dbo.usp_C"
    assert callers[1]["call_count"] == 1


# [함수 설명]
# - 목적: callers function target 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_callers_function_target() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/callers",
        json={
            "target": "dbo.fn_T",
            "target_type": "function",
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        SELECT dbo.fn_T(@x);
                    END
                    """,
                }
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_callers"] is True
    assert payload["summary"]["caller_count"] == 1
    assert payload["summary"]["total_calls"] == 1
    assert payload["callers"][0]["call_kinds"] == ["function_call"]

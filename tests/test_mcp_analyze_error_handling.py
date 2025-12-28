# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: mcp analyze error handling simple 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_analyze_error_handling_simple() -> None:
    client = TestClient(app)
    payload = {"sql": "SELECT 1", "dialect": "tsql"}

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    error_handling = data["error_handling"]
    assert error_handling["has_try_catch"] is False
    assert error_handling["try_count"] == 0
    assert error_handling["catch_count"] == 0
    assert error_handling["uses_throw"] is False
    assert error_handling["throw_count"] == 0
    assert error_handling["uses_raiserror"] is False
    assert error_handling["raiserror_count"] == 0
    assert error_handling["uses_at_at_error"] is False
    assert error_handling["at_at_error_count"] == 0
    assert error_handling["uses_error_functions"] == []
    assert error_handling["uses_print"] is False
    assert error_handling["print_count"] == 0
    assert error_handling["uses_return"] is False
    assert error_handling["return_count"] == 0
    assert error_handling["return_values"] == []
    assert error_handling["uses_output_error_params"] is False
    assert error_handling["output_error_params"] == []
    assert error_handling["signals"] == []


# [함수 설명]
# - 목적: mcp analyze error handling try catch throw 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_analyze_error_handling_try_catch_throw() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        BEGIN TRY
            SELECT 1;
        END TRY
        BEGIN CATCH
            DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
            THROW;
        END CATCH
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    error_handling = response.json()["error_handling"]
    assert error_handling["has_try_catch"] is True
    assert error_handling["try_count"] == 1
    assert error_handling["catch_count"] == 1
    assert error_handling["uses_throw"] is True
    assert error_handling["throw_count"] >= 1
    assert "ERROR_MESSAGE" in error_handling["uses_error_functions"]
    assert "TRY/CATCH" in error_handling["signals"]
    assert "THROW" in error_handling["signals"]
    assert "ERROR_MESSAGE" in error_handling["signals"]


# [함수 설명]
# - 목적: mcp analyze error handling raiserror ataterror return 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_analyze_error_handling_raiserror_ataterror_return() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        RAISERROR('bad', 16, 1);
        IF @@ERROR <> 0
            RETURN -1;
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    error_handling = response.json()["error_handling"]
    assert error_handling["uses_raiserror"] is True
    assert error_handling["raiserror_count"] >= 1
    assert error_handling["uses_at_at_error"] is True
    assert error_handling["at_at_error_count"] >= 1
    assert error_handling["uses_return"] is True
    assert -1 in error_handling["return_values"]
    assert "RAISERROR" in error_handling["signals"]
    assert "@@ERROR" in error_handling["signals"]
    assert "RETURN" in error_handling["signals"]

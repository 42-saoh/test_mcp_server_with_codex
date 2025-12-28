# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: mcp analyze transactions absent 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_analyze_transactions_absent() -> None:
    client = TestClient(app)
    payload = {
        "sql": "SELECT 1",
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    transactions = data["transactions"]
    assert transactions["uses_transaction"] is False
    assert transactions["begin_count"] == 0
    assert transactions["commit_count"] == 0
    assert transactions["rollback_count"] == 0
    assert transactions["savepoint_count"] == 0
    assert transactions["has_try_catch"] is False
    assert transactions["xact_abort"] is None
    assert transactions["isolation_level"] is None


# [함수 설명]
# - 목적: mcp analyze transactions present 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_analyze_transactions_present() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        SET XACT_ABORT ON;
        SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
        BEGIN TRY
            BEGIN TRAN
            SELECT @@TRANCOUNT;
            COMMIT TRANSACTION;
        END TRY
        BEGIN CATCH
            IF XACT_STATE() <> 0
                ROLLBACK TRAN;
            THROW;
        END CATCH
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    transactions = data["transactions"]
    assert transactions["uses_transaction"] is True
    assert transactions["begin_count"] == 1
    assert transactions["commit_count"] == 1
    assert transactions["rollback_count"] == 1
    assert transactions["savepoint_count"] == 0
    assert transactions["has_try_catch"] is True
    assert transactions["xact_abort"] == "ON"
    assert transactions["isolation_level"] == "READ COMMITTED"
    assert "BEGIN TRAN" in transactions["signals"]
    assert "COMMIT" in transactions["signals"]
    assert "ROLLBACK" in transactions["signals"]
    assert "TRY/CATCH" in transactions["signals"]
    assert "XACT_ABORT ON" in transactions["signals"]
    assert "ISOLATION LEVEL READ COMMITTED" in transactions["signals"]
    assert "@@TRANCOUNT" in transactions["signals"]
    assert "XACT_STATE()" in transactions["signals"]
    assert "THROW" in transactions["signals"]

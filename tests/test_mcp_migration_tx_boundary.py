# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: tx boundary read only 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_tx_boundary_read_only() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "none"
    assert summary["transactional"] is False
    assert summary["propagation"] == "SUPPORTS"
    assert summary["read_only"] is True
    assert summary["confidence"] >= 0.8


# [함수 설명]
# - 목적: tx boundary writes service layer 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_tx_boundary_writes_service_layer() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_Write",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Write AS INSERT INTO dbo.AuditLog(id) VALUES (1);",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "service_layer"
    assert summary["transactional"] is True
    assert summary["propagation"] == "REQUIRED"


# [함수 설명]
# - 목적: tx boundary hybrid with transaction signals 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_tx_boundary_hybrid_with_transaction_signals() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/migration/transaction-boundary",
        json={
            "name": "dbo.usp_TxManaged",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_TxManaged AS
            BEGIN
                SET XACT_ABORT ON;
                SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
                BEGIN TRY
                    BEGIN TRAN;
                    INSERT INTO dbo.AuditLog(id) VALUES (1);
                    COMMIT TRAN;
                END TRY
                BEGIN CATCH
                    ROLLBACK TRAN;
                    THROW;
                END CATCH
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["recommended_boundary"] == "hybrid"
    assert summary["isolation_level"]

    suggestion_ids = {item["id"] for item in payload["suggestions"]}
    assert "SUG_AVOID_DOUBLE_TX" in suggestion_ids
    assert "SUG_USE_NOT_SUPPORTED" in suggestion_ids


# [함수 설명]
# - 목적: tx boundary determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_tx_boundary_determinism() -> None:
    client = TestClient(app)

    request_payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_items": 10},
    }

    response_first = client.post(
        "/mcp/migration/transaction-boundary",
        json=request_payload,
    )
    response_second = client.post(
        "/mcp/migration/transaction-boundary",
        json=request_payload,
    )

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

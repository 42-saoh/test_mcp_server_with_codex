# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: reusability read only lookup 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_reusability_read_only_lookup() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/reusability",
        json={
            "name": "dbo.usp_ReadOnly",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_ReadOnly AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["score"] >= 80
    assert summary["grade"] in {"A", "B"}
    assert summary["is_candidate"] is True
    assert summary["candidate_type"] == "lookup"

    signals = payload["signals"]
    assert signals["read_only"] is True
    assert signals["has_writes"] is False


# [함수 설명]
# - 목적: reusability dynamic cursor transaction writes 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_reusability_dynamic_cursor_transaction_writes() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/reusability",
        json={
            "name": "dbo.usp_Bad",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Bad AS
            BEGIN
                BEGIN TRAN;
                DECLARE c CURSOR FOR SELECT id FROM dbo.Users;
                OPEN c;
                FETCH NEXT FROM c;
                EXEC sp_executesql N'SELECT 1';
                INSERT INTO dbo.AuditLog(id) VALUES (1);
                COMMIT TRAN;
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    summary = payload["summary"]
    assert summary["score"] < 50
    assert summary["grade"] == "D"
    assert summary["is_candidate"] is False

    reason_ids = {reason["id"] for reason in payload["reasons"]}
    assert "RSN_DYN_SQL" in reason_ids
    assert "RSN_CURSOR" in reason_ids
    assert "RSN_TXN" in reason_ids
    assert "RSN_WRITES" in reason_ids


# [함수 설명]
# - 목적: reusability determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_reusability_determinism() -> None:
    client = TestClient(app)

    payload = {
        "name": "dbo.usp_Same",
        "type": "procedure",
        "sql": "CREATE PROCEDURE dbo.usp_Same AS SELECT 1;",
        "options": {"max_reason_items": 10},
    }

    response_first = client.post("/mcp/common/reusability", json=payload)
    response_second = client.post("/mcp/common/reusability", json=payload)

    assert response_first.status_code == 200
    assert response_second.status_code == 200
    assert response_first.json() == response_second.json()

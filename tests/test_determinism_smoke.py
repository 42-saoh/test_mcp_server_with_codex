# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: determinism smoke endpoints 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_determinism_smoke_endpoints() -> None:
    client = TestClient(app)

    analyze_payload = {
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic AS
        BEGIN
            BEGIN TRAN;
            SELECT id FROM dbo.Users;
            UPDATE dbo.Users SET name = 'x' WHERE id = 1;
            COMMIT TRAN;
        END
        """,
        "dialect": "tsql",
    }

    first = client.post("/mcp/analyze", json=analyze_payload)
    second = client.post("/mcp/analyze", json=analyze_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    mapping_payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": analyze_payload["sql"],
    }

    first = client.post("/mcp/migration/mapping-strategy", json=mapping_payload)
    second = client.post("/mcp/migration/mapping-strategy", json=mapping_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

    perf_payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": analyze_payload["sql"],
    }

    first = client.post("/mcp/quality/performance-risk", json=perf_payload)
    second = client.post("/mcp/quality/performance-risk", json=perf_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

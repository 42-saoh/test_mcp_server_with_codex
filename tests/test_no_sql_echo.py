# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app

SENTINEL = "SQL_SENTINEL__FROM_DBO"


# [함수 설명]
# - 목적: no sql echo analyze 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_no_sql_echo_analyze() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/analyze",
        json={
            "sql": f"SELECT * FROM dbo.Users WHERE note = '{SENTINEL}';",
            "dialect": "tsql",
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text


# [함수 설명]
# - 목적: no sql echo standardize spec 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_no_sql_echo_standardize_spec() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_NoEcho", "type": "procedure"},
            "sql": f"CREATE PROCEDURE dbo.usp_NoEcho AS SELECT '{SENTINEL}';",
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text


# [함수 설명]
# - 목적: no sql echo standardize spec with evidence 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_no_sql_echo_standardize_spec_with_evidence(tmp_path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "placeholder.md").write_text(
        "# Placeholder Doc\n\nUse documented patterns for migrations.",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_NoEchoEvidence", "type": "procedure"},
            "sql": f"CREATE PROCEDURE dbo.usp_NoEchoEvidence AS SELECT '{SENTINEL}';",
            "options": {"docs_dir": str(docs_dir), "top_k": 3},
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text

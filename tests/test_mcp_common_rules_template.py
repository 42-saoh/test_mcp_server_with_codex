# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: rules template no rules 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_rules_template_no_rules() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Simple",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Simple AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["has_rules"] is False
    assert payload["summary"]["rule_count"] == 0
    assert payload["summary"]["template_suggestion_count"] == 0


# [함수 설명]
# - 목적: rules template guard throw 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_rules_template_guard_throw() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Guard",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Guard @p INT AS
            BEGIN
                IF @p IS NULL
                BEGIN
                    THROW 50000, 'missing', 1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["has_rules"] is True
    assert payload["summary"]["rule_count"] == 1
    rule = payload["rules"][0]
    assert rule["kind"] == "guard_clause"
    assert rule["action"] == "raise_error"

    template_ids = {item["template_id"] for item in payload["template_suggestions"]}
    assert "TPL_VALIDATE_REQUIRED_PARAM" in template_ids
    assert "TPL_ERROR_TO_EXCEPTION" in template_ids


# [함수 설명]
# - 목적: rules template exists raiserror 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_rules_template_exists_raiserror() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Exists",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Exists @id INT AS
            BEGIN
                IF EXISTS (SELECT 1 FROM dbo.Users WHERE id = @id)
                BEGIN
                    RAISERROR('exists', 16, 1);
                    RETURN -1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    kinds = {rule["kind"] for rule in payload["rules"]}
    assert "exists_check" in kinds
    template_ids = {item["template_id"] for item in payload["template_suggestions"]}
    assert "TPL_ENSURE_EXISTS" in template_ids
    assert "TPL_ERROR_TO_EXCEPTION" in template_ids


# [함수 설명]
# - 목적: rules template ignores comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_rules_template_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Comments",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Comments @p INT AS
            BEGIN
                -- IF EXISTS (SELECT 1 FROM dbo.Table)
                SELECT 'IF @p IS NULL THEN THROW' AS Note;
                IF @p IS NULL
                BEGIN
                    RETURN 1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["rule_count"] == 1
    kinds = {rule["kind"] for rule in payload["rules"]}
    assert kinds == {"guard_clause"}

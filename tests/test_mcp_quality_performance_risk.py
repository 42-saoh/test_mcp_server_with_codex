# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: _post 처리 로직을 수행한다.
# - 입력: payload: dict
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _post(payload: dict) -> dict:
    client = TestClient(app)
    response = client.post("/mcp/quality/performance-risk", json=payload)
    assert response.status_code == 200
    return response.json()


# [함수 설명]
# - 목적: mcp quality performance risk low 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_performance_risk_low() -> None:
    payload = {
        "name": "dbo.usp_ReadOnly",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_ReadOnly
        AS
        SELECT col1, col2
        FROM dbo.Accounts
        WHERE col1 = 1;
        """,
        "options": {"dialect": "tsql"},
    }

    data = _post(payload)

    assert data["summary"]["risk_level"] == "low"
    assert data["summary"]["risk_score"] <= 24
    severities = {finding["severity"] for finding in data["findings"]}
    assert "critical" not in severities
    assert "high" not in severities


# [함수 설명]
# - 목적: mcp quality performance risk bad patterns 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_performance_risk_bad_patterns() -> None:
    payload = {
        "name": "dbo.usp_Bad",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Bad
        AS
        SELECT *
        FROM dbo.Customers WITH (NOLOCK)
        WHERE UPPER(name) LIKE '%x';
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert {
        "PRF_SELECT_STAR",
        "PRF_LEADING_WILDCARD_LIKE",
        "PRF_FUNCTION_ON_COLUMN",
        "PRF_NOLOCK",
    }.issubset(finding_ids)
    assert data["summary"]["risk_level"] in {"medium", "high", "critical"}


# [함수 설명]
# - 목적: mcp quality performance risk cursor and dynamic sql 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_performance_risk_cursor_and_dynamic_sql() -> None:
    payload = {
        "name": "dbo.usp_Cursor",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Cursor
        AS
        DECLARE cur CURSOR FOR SELECT id FROM dbo.Items;
        OPEN cur;
        WHILE 1 = 1
        BEGIN
            EXEC(@sql);
            UPDATE dbo.Items SET name = name;
            FETCH NEXT FROM cur;
        END
        CLOSE cur;
        DEALLOCATE cur;
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert "PRF_CURSOR_RBAR" in finding_ids
    assert "PRF_DYNAMIC_SQL" in finding_ids
    assert "PRF_LOOP_RBAR" in finding_ids
    assert data["summary"]["risk_level"] in {"high", "critical"}


# [함수 설명]
# - 목적: mcp quality performance risk ignores comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_performance_risk_ignores_comments_and_strings() -> None:
    payload = {
        "name": "dbo.usp_Comments",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Comments
        AS
        -- SELECT * FROM dbo.Hidden WITH (NOLOCK)
        /* NOLOCK should not count */
        SELECT col1, 'SELECT * NOLOCK' AS note
        FROM dbo.Visible;
        """,
    }

    data = _post(payload)

    finding_ids = {finding["id"] for finding in data["findings"]}
    assert "PRF_SELECT_STAR" not in finding_ids
    assert "PRF_NOLOCK" not in finding_ids


# [함수 설명]
# - 목적: mcp quality performance risk determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_performance_risk_determinism() -> None:
    payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic
        AS
        SELECT *
        FROM dbo.Orders
        WHERE amount IN (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20);
        """,
    }

    first = _post(payload)
    second = _post(payload)

    assert first == second

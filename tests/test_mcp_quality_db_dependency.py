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
    response = client.post("/mcp/quality/db-dependency", json=payload)
    assert response.status_code == 200
    return response.json()


# [함수 설명]
# - 목적: mcp quality db dependency low 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_db_dependency_low() -> None:
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
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] == "low"
    assert data["metrics"]["linked_server_count"] == 0
    assert data["metrics"]["cross_database_count"] == 0


# [함수 설명]
# - 목적: mcp quality db dependency cross db and linked server 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_db_dependency_cross_db_and_linked_server() -> None:
    payload = {
        "name": "dbo.usp_Dep",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Dep
        AS
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
        """,
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] in {"high", "critical"}
    assert data["metrics"]["linked_server_count"] == 1
    assert data["metrics"]["cross_database_count"] == 1
    assert data["metrics"]["openquery_count"] == 1
    assert data["metrics"]["remote_exec_count"] == 1

    linked_servers = {item["name"] for item in data["dependencies"]["linked_servers"]}
    assert "lsrv1" in linked_servers
    cross_db = {item["database"] for item in data["dependencies"]["cross_database"]}
    assert "otherdb" in cross_db


# [함수 설명]
# - 목적: mcp quality db dependency risky system and clr 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_db_dependency_risky_system_and_clr() -> None:
    payload = {
        "name": "dbo.usp_Risky",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Risky
        AS
        EXEC xp_cmdshell 'dir';
        EXEC sp_OACreate 'scripting.filesystemobject', @obj OUT;
        CREATE ASSEMBLY MyAsm FROM 0x00 WITH PERMISSION_SET = EXTERNAL_ACCESS;
        """,
    }

    data = _post(payload)

    assert data["summary"]["dependency_level"] == "critical"
    reason_ids = {reason["id"] for reason in data["reasons"]}
    assert "RSN_XP_CMDSHELL" in reason_ids
    assert "RSN_CLR" in reason_ids


# [함수 설명]
# - 목적: mcp quality db dependency ignores comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_db_dependency_ignores_comments_and_strings() -> None:
    payload = {
        "name": "dbo.usp_Comments",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Comments
        AS
        -- SELECT * FROM LSRV1.OtherDb.dbo.TableX
        /* OPENQUERY(LSRV1, 'SELECT 1') */
        SELECT col1, 'LSRV1.OtherDb.dbo.TableX OPENQUERY(LSRV1, ...)' AS note
        FROM dbo.Visible;
        """,
    }

    data = _post(payload)

    assert data["metrics"]["linked_server_count"] == 0
    assert data["metrics"]["openquery_count"] == 0
    assert data["metrics"]["cross_database_count"] == 0


# [함수 설명]
# - 목적: mcp quality db dependency determinism 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_mcp_quality_db_dependency_determinism() -> None:
    payload = {
        "name": "dbo.usp_Deterministic",
        "type": "procedure",
        "sql": """
        CREATE PROCEDURE dbo.usp_Deterministic
        AS
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
        """,
    }

    data = _post(payload)
    data_repeat = _post(payload)

    assert data == data_repeat

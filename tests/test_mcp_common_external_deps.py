# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: external deps none 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_external_deps_none() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Simple",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Simple AS SELECT * FROM dbo.TableA;",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"] == {
        "has_external_deps": False,
        "linked_server_count": 0,
        "cross_db_count": 0,
        "remote_exec_count": 0,
        "openquery_count": 0,
        "opendatasource_count": 0,
    }
    assert payload["external_dependencies"] == {
        "linked_servers": [],
        "cross_database": [],
        "remote_exec": [],
        "openquery": [],
        "opendatasource": [],
        "others": [],
    }


# [함수 설명]
# - 목적: external deps multiple patterns 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_external_deps_multiple_patterns() -> None:
    client = TestClient(app)

    sql = """
    CREATE PROCEDURE dbo.usp_Sample AS
    BEGIN
        SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT * FROM OtherDb.dbo.TableY;
        SELECT * FROM OPENQUERY(LSRV1, 'SELECT 1');
        EXEC ('proc') AT LSRV1;
    END
    """

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Sample",
            "type": "procedure",
            "sql": sql,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_external_deps"] is True
    assert payload["summary"]["linked_server_count"] == 1
    assert payload["summary"]["cross_db_count"] == 1
    assert payload["summary"]["remote_exec_count"] == 1
    assert payload["summary"]["openquery_count"] == 1
    assert payload["summary"]["opendatasource_count"] == 0

    linked_servers = payload["external_dependencies"]["linked_servers"]
    assert linked_servers[0]["name"] == "LSRV1"
    assert set(linked_servers[0]["signals"]) == {"EXEC AT", "OPENQUERY", "four_part_name"}

    cross_database = payload["external_dependencies"]["cross_database"]
    assert cross_database == [
        {
            "database": "OtherDb",
            "schema": "dbo",
            "object": "TableY",
            "kind": "three_part_name",
        }
    ]

    remote_exec = payload["external_dependencies"]["remote_exec"]
    assert remote_exec == [{"target": "LSRV1", "kind": "exec_at", "signals": ["EXEC AT"]}]

    openquery = payload["external_dependencies"]["openquery"]
    assert openquery == [{"target": "LSRV1", "kind": "openquery", "signals": ["OPENQUERY"]}]


# [함수 설명]
# - 목적: external deps ignore comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_external_deps_ignore_comments_and_strings() -> None:
    client = TestClient(app)

    sql = """
    CREATE PROCEDURE dbo.usp_Ignore AS
    BEGIN
        -- SELECT * FROM LSRV1.OtherDb.dbo.TableX;
        SELECT 'LSRV1.OtherDb.dbo.TableX' AS Example;
    END
    """

    response = client.post(
        "/mcp/external-deps",
        json={
            "name": "dbo.usp_Ignore",
            "type": "procedure",
            "sql": sql,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["has_external_deps"] is False
    assert payload["summary"]["linked_server_count"] == 0
    assert payload["summary"]["cross_db_count"] == 0
    assert payload["summary"]["remote_exec_count"] == 0
    assert payload["summary"]["openquery_count"] == 0
    assert payload["summary"]["opendatasource_count"] == 0

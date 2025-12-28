# [파일 설명]
# - 목적: API 및 서비스의 기대 동작을 자동으로 검증한다.
# - 제공 기능: 클라이언트 호출과 응답 구조에 대한 단언을 포함한다.
# - 입력/출력: 고정 입력을 사용하며 테스트 통과 여부로 결과를 확인한다.
# - 주의 사항: 원문 SQL이나 비밀 값은 로그/출력에 포함하지 않는다.
# - 연관 모듈: app.main/app.api.mcp 및 서비스 레이어와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: call graph simple corpus 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_call_graph_simple_corpus() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS EXEC dbo.usp_B;",
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT dbo.fn_C(1);",
                },
                {
                    "name": "dbo.fn_C",
                    "type": "function",
                    "sql": "CREATE FUNCTION dbo.fn_C() RETURNS INT AS BEGIN RETURN 1; END",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["object_count"] == 3
    assert payload["summary"]["node_count"] == 3
    assert payload["summary"]["edge_count"] == 2

    assert payload["graph"]["nodes"] == [
        {"id": "dbo.fn_c", "name": "dbo.fn_C", "type": "function"},
        {"id": "dbo.usp_a", "name": "dbo.usp_A", "type": "procedure"},
        {"id": "dbo.usp_b", "name": "dbo.usp_B", "type": "procedure"},
    ]
    assert payload["graph"]["edges"] == [
        {
            "from": "dbo.usp_a",
            "to": "dbo.usp_b",
            "kind": "exec",
            "count": 1,
            "signals": ["EXEC"],
        },
        {
            "from": "dbo.usp_b",
            "to": "dbo.fn_c",
            "kind": "function_call",
            "count": 1,
            "signals": ["FUNCTION"],
        },
    ]


# [함수 설명]
# - 목적: call graph ignores comments and strings 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_call_graph_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC dbo.usp_B;
                        -- EXEC dbo.usp_B
                        SELECT 'EXEC dbo.usp_B';
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT 1;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 1
    assert payload["graph"]["edges"][0]["count"] == 1


# [함수 설명]
# - 목적: call graph ignores dynamic exec 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_call_graph_ignores_dynamic_exec() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": """
                    CREATE PROCEDURE dbo.usp_A AS
                    BEGIN
                        EXEC(@sql);
                        EXEC sp_executesql @sql;
                    END
                    """,
                },
                {
                    "name": "dbo.usp_B",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_B AS SELECT 1;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 0
    assert payload["graph"]["edges"] == []


# [함수 설명]
# - 목적: call graph ambiguous target 동작을 검증한다.
# - 입력: 테스트 픽스처/클라이언트 등 고정 입력을 사용한다.
# - 출력: 예외 없이 단언을 통과하면 성공으로 간주한다.
# - 에러 처리: 실패 시 pytest가 assertion 결과를 보고한다.
# - 결정론: 동일 입력으로 항상 재현 가능한 검증을 수행한다.
# - 보안: 테스트 로그에 원문 SQL/민감 정보를 남기지 않는다.
def test_call_graph_ambiguous_target() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/call-graph",
        json={
            "objects": [
                {
                    "name": "dbo.usp_A",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_A AS EXEC usp_X;",
                },
                {
                    "name": "dbo.usp_X",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE dbo.usp_X AS SELECT 1;",
                },
                {
                    "name": "alt.usp_X",
                    "type": "procedure",
                    "sql": "CREATE PROCEDURE alt.usp_X AS SELECT 2;",
                },
            ]
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["summary"]["edge_count"] == 0
    assert payload["errors"] == [
        {
            "id": "AMBIGUOUS_TARGET",
            "message": "Call to usp_x is ambiguous across schemas.",
            "object": "dbo.usp_A",
        }
    ]

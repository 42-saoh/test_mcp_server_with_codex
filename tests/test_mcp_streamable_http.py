# [파일 설명]
# - 목적: Streamable HTTP MCP 핸드셰이크 및 도구 호출 흐름을 검증한다.
# - 제공 기능: initialize/tools/list/tools/call 시나리오를 테스트한다.
# - 입력/출력: JSON-RPC 메시지를 사용한다.
# - 주의 사항: 원문 SQL/비밀 값은 로그에 포함하지 않는다.
# - 연관 모듈: app.main 및 app.mcp_streamable_http와 연동된다.
from fastapi.testclient import TestClient

from app.main import app


# [함수 설명]
# - 목적: MCP initialize 요청이 정상 응답을 반환하는지 확인한다.
# - 입력: JSON-RPC initialize 메시지
# - 출력: protocolVersion/capabilities/serverInfo 확인
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: SQL 원문/비밀 값은 사용하지 않는다.
def test_mcp_initialize_handshake() -> None:
    client = TestClient(app)

    payload = {
        "jsonrpc": "2.0",
        "id": "init-1",
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "clientInfo": {"name": "vscode", "version": "1.0"},
        },
    }
    response = client.post(
        "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["jsonrpc"] == "2.0"
    assert body["id"] == "init-1"
    result = body["result"]
    assert result["protocolVersion"] == "2025-11-25"
    assert "capabilities" in result
    assert "serverInfo" in result


# [함수 설명]
# - 목적: notifications/initialized 알림이 202를 반환하는지 확인한다.
# - 입력: JSON-RPC notification 메시지
# - 출력: HTTP 202 응답
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: 민감 정보는 포함하지 않는다.
def test_mcp_initialized_notification_returns_202() -> None:
    client = TestClient(app)

    payload = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    response = client.post("/mcp", json=payload)

    assert response.status_code == 202


# [함수 설명]
# - 목적: tools/list 요청이 도구 목록을 반환하는지 확인한다.
# - 입력: JSON-RPC tools/list 메시지
# - 출력: 도구 목록 길이 검증
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: 민감 정보는 포함하지 않는다.
def test_mcp_tools_list_returns_tools() -> None:
    client = TestClient(app)

    payload = {"jsonrpc": "2.0", "id": "list-1", "method": "tools/list", "params": {}}
    response = client.post(
        "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 200
    body = response.json()
    tools = body["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) >= 1


# [함수 설명]
# - 목적: tools/call 요청이 분석 결과를 반환하는지 확인한다.
# - 입력: JSON-RPC tools/call 메시지
# - 출력: content 및 structuredContent 확인
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: SQL 원문은 테스트 내부에서만 사용한다.
def test_mcp_tools_call_returns_result() -> None:
    client = TestClient(app)

    payload = {
        "jsonrpc": "2.0",
        "id": "call-1",
        "method": "tools/call",
        "params": {
            "name": "tsql.analyze",
            "arguments": {"sql": "SELECT 1", "dialect": "tsql"},
        },
    }
    response = client.post(
        "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "2025-11-25"},
    )

    assert response.status_code == 200
    body = response.json()
    result = body["result"]
    assert result["content"]
    assert "structuredContent" in result


# [함수 설명]
# - 목적: GET /mcp가 405를 반환하는지 확인한다.
# - 입력: GET 요청
# - 출력: HTTP 405 응답
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: 민감 정보는 포함하지 않는다.
def test_mcp_get_returns_405() -> None:
    client = TestClient(app)

    response = client.get("/mcp")

    assert response.status_code == 405


# [함수 설명]
# - 목적: 지원되지 않는 MCP-Protocol-Version이 400을 반환하는지 확인한다.
# - 입력: 잘못된 MCP-Protocol-Version 헤더
# - 출력: HTTP 400 응답
# - 에러 처리: 실패 시 pytest assertion으로 보고한다.
# - 결정론: 동일 입력에 대해 동일 결과를 검증한다.
# - 보안: 민감 정보는 포함하지 않는다.
def test_mcp_invalid_protocol_version_returns_400() -> None:
    client = TestClient(app)

    payload = {"jsonrpc": "2.0", "id": "init-2", "method": "initialize", "params": {}}
    response = client.post(
        "/mcp",
        json=payload,
        headers={"MCP-Protocol-Version": "1900-01-01"},
    )

    assert response.status_code == 400

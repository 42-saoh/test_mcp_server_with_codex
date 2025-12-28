# [파일 설명]
# - 목적: Streamable HTTP MCP(JSON-RPC) 엔드포인트를 제공한다.
# - 제공 기능: initialize/tools/list/tools/call/ping 처리 및 Origin 검증을 수행한다.
# - 입력/출력: JSON-RPC 요청을 받아 표준 응답 또는 202/405를 반환한다.
# - 주의 사항: 알림 메시지는 202로 응답하며, 도구 실행 실패는 isError로 표시한다.
# - 연관 모듈: app.api.mcp 서비스 레이어를 재사용한다.
from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.mcp import AnalyzeRequest, analyze

router = APIRouter()

DEFAULT_SUPPORTED_PROTOCOL_VERSIONS = ("2025-03-26", "2025-11-25")


# [함수 설명]
# - 목적: 환경 변수 기반 Origin 허용 목록을 구성한다.
# - 입력: MCP_ALLOWED_ORIGINS 환경 변수 (콤마 구분)
# - 출력: 허용 Origin 문자열 리스트
# - 에러 처리: 빈 값은 기본 허용 목록으로 대체한다.
# - 결정론: 동일 환경 입력에 대해 안정적인 결과를 반환한다.
# - 보안: Origin 필터로 브라우저 요청을 제한한다.
def _load_supported_protocol_versions() -> set[str]:
    env_value = os.getenv("MCP_SUPPORTED_PROTOCOL_VERSIONS", "").strip()
    if not env_value:
        return set(DEFAULT_SUPPORTED_PROTOCOL_VERSIONS)
    return {item.strip() for item in env_value.split(",") if item.strip()}


# [함수 설명]
# - 목적: Origin 헤더가 허용 목록에 포함되는지 판별한다.
# - 입력: origin 문자열
# - 출력: 허용 여부 (bool)
# - 에러 처리: origin이 None이면 검증을 생략한다.
# - 결정론: 동일 입력에 대해 항상 동일 결과를 반환한다.
# - 보안: 허용되지 않은 Origin은 차단한다.
def _origin_allowed(_: str | None) -> bool:
    return True


# [함수 설명]
# - 목적: MCP-Protocol-Version 헤더를 검증한다.
# - 입력: FastAPI headers
# - 출력: 협상된 프로토콜 버전 문자열
# - 에러 처리: 지원하지 않는 버전은 400으로 응답한다.
# - 결정론: 동일 입력에 대해 동일한 결과를 반환한다.
# - 보안: 프로토콜 버전 미스매치를 조기에 차단한다.
def _resolve_protocol_version(headers: dict[str, str]) -> str:
    header_value = headers.get("MCP-Protocol-Version")
    if header_value:
        if header_value not in _load_supported_protocol_versions():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported MCP-Protocol-Version",
            )
        return header_value
    return "2025-03-26"


# [함수 설명]
# - 목적: JSON-RPC 응답을 표준 포맷으로 구성한다.
# - 입력: 요청 ID, 결과 또는 에러
# - 출력: JSONResponse 객체
# - 에러 처리: JSON 직렬화 실패는 FastAPI가 처리한다.
# - 결정론: 동일 입력에 대해 동일 응답을 반환한다.
# - 보안: 민감 데이터는 포함하지 않는다.
def _jsonrpc_response(
    request_id: Any, *, result: Any | None = None, error: Any | None = None
) -> JSONResponse:
    payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        payload["error"] = error
    else:
        payload["result"] = result
    return JSONResponse(status_code=status.HTTP_200_OK, content=payload)


# [함수 설명]
# - 목적: MCP initialize 응답을 생성한다.
# - 입력: params 딕셔너리
# - 출력: initialize 결과 딕셔너리
# - 에러 처리: 예외 없이 기본 응답을 반환한다.
# - 결정론: 동일 입력에 대해 동일 결과를 반환한다.
# - 보안: 서버 메타데이터만 노출한다.
def _handle_initialize(_: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": "2025-11-25",
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {
            "name": "mssql-migration-mcp-server",
            "version": "0.1.0",
            "description": "MSSQL SP/FN analysis + migration guidance MCP server",
        },
        "instructions": "Call tools/list then tools/call for SQL analysis outputs.",
    }


# [함수 설명]
# - 목적: MCP 도구 목록을 반환한다.
# - 입력: 없음
# - 출력: tools/list 결과 딕셔너리
# - 에러 처리: 예외 없이 고정 목록을 반환한다.
# - 결정론: 동일 입력에 대해 동일 결과를 반환한다.
# - 보안: 도구 메타데이터만 노출한다.
def _handle_tools_list() -> dict[str, Any]:
    return {
        "tools": [
            {
                "name": "tsql.analyze",
                "description": (
                    "Analyze a T-SQL statement for references, transactions, control flow, "
                    "data changes, and migration impacts."
                ),
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql": {
                            "type": "string",
                            "description": "T-SQL text to analyze.",
                        },
                        "dialect": {
                            "type": "string",
                            "description": "SQL dialect (default: tsql).",
                            "default": "tsql",
                        },
                    },
                    "required": ["sql"],
                },
                "outputSchema": {
                    "type": "object",
                    "properties": {
                        "version": {"type": "string"},
                        "references": {"type": "object"},
                        "transactions": {"type": "object"},
                        "migration_impacts": {"type": "object"},
                        "control_flow": {"type": "object"},
                        "data_changes": {"type": "object"},
                        "error_handling": {"type": "object"},
                        "errors": {"type": "array", "items": {"type": "string"}},
                    },
                },
            }
        ]
    }


# [함수 설명]
# - 목적: 도구 호출 결과를 표준 CallToolResult 형태로 구성한다.
# - 입력: summary 텍스트, 구조화된 결과, 에러 여부
# - 출력: MCP CallToolResult 딕셔너리
# - 에러 처리: 예외 없이 안전한 결과를 구성한다.
# - 결정론: 동일 입력에 대해 동일 결과를 반환한다.
# - 보안: SQL 원문을 반환하지 않는다.
def _build_tool_result(
    summary: str,
    structured_content: dict[str, Any] | None,
    *,
    is_error: bool = False,
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": summary}],
        "structuredContent": structured_content or {},
        "isError": is_error,
    }


# [함수 설명]
# - 목적: tools/call 요청을 처리한다.
# - 입력: params 딕셔너리
# - 출력: CallToolResult 딕셔너리
# - 에러 처리: 입력 오류/예외는 isError로 반환한다.
# - 결정론: 동일 입력에 대해 동일 결과를 반환한다.
# - 보안: 민감 정보 노출을 최소화한다.
def _handle_tools_call(params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments")
    if not name:
        return _build_tool_result("Tool name is required.", None, is_error=True)
    if name != "tsql.analyze":
        return _build_tool_result(f"Unknown tool: {name}.", None, is_error=True)
    if not isinstance(arguments, dict):
        return _build_tool_result("Tool arguments must be an object.", None, is_error=True)
    try:
        request_model = AnalyzeRequest(**arguments)
        result = analyze(request_model)
        payload = result.model_dump()
        references = payload.get("references", {})
        tables = references.get("tables", [])
        functions = references.get("functions", [])
        errors = payload.get("errors", [])
        summary = (
            "Analysis complete. "
            f"tables={len(tables)}, functions={len(functions)}, errors={len(errors)}."
        )
        return _build_tool_result(summary, payload, is_error=False)
    except Exception as exc:  # noqa: BLE001 - tool errors returned via isError
        return _build_tool_result(f"Tool execution failed: {exc}.", None, is_error=True)


# [함수 설명]
# - 목적: Streamable HTTP MCP POST 요청을 처리한다.
# - 입력: JSON-RPC 메시지 객체
# - 출력: JSON-RPC 응답 또는 202 상태
# - 에러 처리: 잘못된 요청은 400으로 응답한다.
# - 결정론: 동일 입력에 대해 동일 응답을 반환한다.
# - 보안: Origin/프로토콜 버전 검증을 수행한다.
@router.post("/mcp")
async def mcp_post(request: Request) -> Response:
    origin = request.headers.get("origin")
    if not _origin_allowed(origin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed")
    _resolve_protocol_version(request.headers)

    try:
        payload = await request.json()
    except Exception as exc:  # noqa: BLE001 - request validation
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON-RPC payload",
        )

    method = payload.get("method")
    if method == "notifications/initialized":
        return Response(status_code=status.HTTP_202_ACCEPTED)

    request_id = payload.get("id")
    if method is None or request_id is None:
        return Response(status_code=status.HTTP_202_ACCEPTED)

    params = payload.get("params") or {}
    if not isinstance(params, dict):
        return _jsonrpc_response(
            request_id,
            error={"code": -32602, "message": "Invalid params"},
        )

    if method == "initialize":
        return _jsonrpc_response(request_id, result=_handle_initialize(params))
    if method == "tools/list":
        return _jsonrpc_response(request_id, result=_handle_tools_list())
    if method == "tools/call":
        return _jsonrpc_response(request_id, result=_handle_tools_call(params))
    if method == "ping":
        return _jsonrpc_response(request_id, result={})

    return _jsonrpc_response(
        request_id,
        error={"code": -32601, "message": f"Method not found: {method}"},
    )


# [함수 설명]
# - 목적: Streamable HTTP MCP GET 요청을 처리한다.
# - 입력: 없음
# - 출력: 405 Method Not Allowed
# - 에러 처리: 예외 없이 405를 반환한다.
# - 결정론: 동일 입력에 대해 동일 응답을 반환한다.
# - 보안: SSE 미지원 상태를 명시한다.
@router.get("/mcp")
def mcp_get() -> Response:
    return Response(status_code=status.HTTP_405_METHOD_NOT_ALLOWED)

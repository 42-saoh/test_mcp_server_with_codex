# [파일 설명]
# - 목적: FastAPI 애플리케이션을 생성하고 라우터를 조립한다.
# - 제공 기능: /health 엔드포인트와 MCP 라우터 등록을 제공한다.
# - 입력/출력: HTTP 요청에 대해 상태 정보를 반환한다.
# - 주의 사항: 동작 변경 없이 라우팅만 담당한다.
# - 연관 모듈: app.api.mcp 라우터와 연동된다.
from fastapi import FastAPI, Request, Response

from app.api.mcp import router as mcp_router
from app.mcp_streamable_http import mcp_get, mcp_post

app = FastAPI()


# [함수 설명]
# - 목적: 서비스 상태 확인을 위한 헬스 체크 응답을 제공한다.
# - 입력: 요청 바디 없이 호출된다.
# - 출력: status 필드를 포함한 간단한 상태 응답을 반환한다.
# - 에러 처리: 내부 예외 없이 즉시 성공 응답을 반환한다.
# - 결정론: 항상 동일한 상태 값을 반환하도록 유지한다.
# - 보안: 민감 정보는 응답에 포함하지 않는다.
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(mcp_router, prefix="/mcp")


@app.post("/mcp")
async def mcp_post_route(request: Request) -> Response:
    return await mcp_post(request)


@app.get("/mcp")
def mcp_get_route() -> Response:
    return mcp_get()

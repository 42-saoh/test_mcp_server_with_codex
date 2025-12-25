from fastapi import FastAPI

from app.api.mcp import router as mcp_router

app = FastAPI()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(mcp_router, prefix="/mcp")

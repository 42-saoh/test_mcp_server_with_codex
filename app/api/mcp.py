from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tsql_analyzer import analyze_references

router = APIRouter()


class AnalyzeRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    dialect: str = "tsql"


class References(BaseModel):
    tables: list[str]
    functions: list[str]


class AnalyzeResponse(BaseModel):
    version: str
    references: References
    errors: list[str]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = analyze_references(request.sql, request.dialect)
    return AnalyzeResponse(
        version="0.1",
        references=References(**result["references"]),
        errors=result["errors"],
    )

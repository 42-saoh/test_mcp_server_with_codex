from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tsql_analyzer import (
    analyze_migration_impacts,
    analyze_references,
    analyze_transactions,
)

router = APIRouter()


class AnalyzeRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    dialect: str = "tsql"


class References(BaseModel):
    tables: list[str]
    functions: list[str]


class TransactionSummary(BaseModel):
    uses_transaction: bool
    begin_count: int
    commit_count: int
    rollback_count: int
    savepoint_count: int
    has_try_catch: bool
    xact_abort: str | None
    isolation_level: str | None
    signals: list[str]


class ImpactItem(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    signals: list[str]
    details: str


class MigrationImpacts(BaseModel):
    has_impact: bool
    items: list[ImpactItem]


class AnalyzeResponse(BaseModel):
    version: str
    references: References
    transactions: TransactionSummary
    migration_impacts: MigrationImpacts
    errors: list[str]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = analyze_references(request.sql, request.dialect)
    transactions = analyze_transactions(request.sql)
    impacts = analyze_migration_impacts(request.sql)
    return AnalyzeResponse(
        version="0.3",
        references=References(**result["references"]),
        transactions=TransactionSummary(**transactions),
        migration_impacts=MigrationImpacts(**impacts),
        errors=result["errors"],
    )

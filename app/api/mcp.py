from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tsql_analyzer import (
    analyze_control_flow,
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


class ControlFlowSummary(BaseModel):
    has_branching: bool
    has_loops: bool
    has_try_catch: bool
    has_goto: bool
    has_return: bool
    branch_count: int
    loop_count: int
    return_count: int
    goto_count: int
    max_nesting_depth: int
    cyclomatic_complexity: int


class ControlFlowNode(BaseModel):
    id: str
    type: str
    label: str


class ControlFlowEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    label: str


class ControlFlowGraph(BaseModel):
    nodes: list[ControlFlowNode]
    edges: list[ControlFlowEdge]


class ControlFlow(BaseModel):
    summary: ControlFlowSummary
    graph: ControlFlowGraph
    signals: list[str]


class AnalyzeResponse(BaseModel):
    version: str
    references: References
    transactions: TransactionSummary
    migration_impacts: MigrationImpacts
    control_flow: ControlFlow
    errors: list[str]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = analyze_references(request.sql, request.dialect)
    transactions = analyze_transactions(request.sql)
    impacts = analyze_migration_impacts(request.sql)
    control_flow = analyze_control_flow(request.sql, request.dialect)
    errors = result["errors"] + control_flow["errors"]
    return AnalyzeResponse(
        version="0.4",
        references=References(**result["references"]),
        transactions=TransactionSummary(**transactions),
        migration_impacts=MigrationImpacts(**impacts),
        control_flow=ControlFlow(**control_flow["control_flow"]),
        errors=errors,
    )

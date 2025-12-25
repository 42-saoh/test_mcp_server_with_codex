from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.tsql_analyzer import (
    analyze_control_flow,
    analyze_data_changes,
    analyze_error_handling,
    analyze_migration_impacts,
    analyze_references,
    analyze_transactions,
)
from app.services.tsql_callers import (
    CallerOptions as ServiceCallerOptions,
)
from app.services.tsql_callers import (
    SqlObject as ServiceSqlObject,
)
from app.services.tsql_callers import (
    find_callers,
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


class DataChangeOperation(BaseModel):
    count: int
    tables: list[str]


class DataChangeOperations(BaseModel):
    insert: DataChangeOperation
    update: DataChangeOperation
    delete: DataChangeOperation
    merge: DataChangeOperation
    truncate: DataChangeOperation
    select_into: DataChangeOperation


class TableOperation(BaseModel):
    table: str
    ops: list[str]


class DataChanges(BaseModel):
    has_writes: bool
    operations: DataChangeOperations
    table_operations: list[TableOperation]
    signals: list[str]
    notes: list[str]


class ErrorHandling(BaseModel):
    has_try_catch: bool
    try_count: int
    catch_count: int
    uses_throw: bool
    throw_count: int
    uses_raiserror: bool
    raiserror_count: int
    uses_at_at_error: bool
    at_at_error_count: int
    uses_error_functions: list[str]
    uses_print: bool
    print_count: int
    uses_return: bool
    return_count: int
    return_values: list[int]
    uses_output_error_params: bool
    output_error_params: list[str]
    signals: list[str]
    notes: list[str]


class AnalyzeResponse(BaseModel):
    version: str
    references: References
    transactions: TransactionSummary
    migration_impacts: MigrationImpacts
    control_flow: ControlFlow
    data_changes: DataChanges
    error_handling: ErrorHandling
    errors: list[str]


class CallersOptions(BaseModel):
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_self: bool = False


class CallersObject(BaseModel):
    name: str
    type: str
    sql: str


class CallersRequest(BaseModel):
    target: str
    target_type: str | None = None
    objects: list[CallersObject]
    options: CallersOptions = Field(default_factory=CallersOptions)


class CallersTarget(BaseModel):
    name: str
    type: str
    normalized: str


class CallersSummary(BaseModel):
    has_callers: bool
    caller_count: int
    total_calls: int


class CallerResult(BaseModel):
    name: str
    type: str
    call_count: int
    call_kinds: list[str]
    signals: list[str]


class CallersResponse(BaseModel):
    version: str
    target: CallersTarget
    summary: CallersSummary
    callers: list[CallerResult]
    errors: list[str]


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    result = analyze_references(request.sql, request.dialect)
    transactions = analyze_transactions(request.sql)
    impacts = analyze_migration_impacts(request.sql)
    control_flow = analyze_control_flow(request.sql, request.dialect)
    data_changes = analyze_data_changes(request.sql, request.dialect)
    error_handling = analyze_error_handling(request.sql)
    errors = result["errors"] + control_flow["errors"] + data_changes["errors"]
    return AnalyzeResponse(
        version="0.6",
        references=References(**result["references"]),
        transactions=TransactionSummary(**transactions),
        migration_impacts=MigrationImpacts(**impacts),
        control_flow=ControlFlow(**control_flow["control_flow"]),
        data_changes=DataChanges(**data_changes["data_changes"]),
        error_handling=ErrorHandling(**error_handling),
        errors=errors,
    )


@router.post("/callers", response_model=CallersResponse)
def callers(request: CallersRequest) -> CallersResponse:
    target_type = _infer_target_type(request.target, request.target_type)
    service_objects = [
        ServiceSqlObject(name=obj.name, type=obj.type, sql=obj.sql) for obj in request.objects
    ]
    service_options = ServiceCallerOptions(
        case_insensitive=request.options.case_insensitive,
        schema_sensitive=request.options.schema_sensitive,
        include_self=request.options.include_self,
    )
    result = find_callers(request.target, target_type, service_objects, service_options)
    return CallersResponse(**result)


def _infer_target_type(target: str, target_type: str | None) -> str:
    if target_type:
        return target_type.lower()
    if "(" in target:
        return "function"
    return "procedure"

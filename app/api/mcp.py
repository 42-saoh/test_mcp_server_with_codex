from __future__ import annotations

from typing import Literal

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
from app.services.tsql_business_rules import analyze_business_rules
from app.services.tsql_call_graph import (
    Options as ServiceCallGraphOptions,
)
from app.services.tsql_call_graph import (
    SqlObject as ServiceCallGraphObject,
)
from app.services.tsql_call_graph import (
    build_call_graph,
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
from app.services.tsql_external_deps import analyze_external_dependencies
from app.services.tsql_mapping_strategy import recommend_mapping_strategy
from app.services.tsql_reusability import evaluate_reusability

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


class ExternalDepsOptions(BaseModel):
    case_insensitive: bool = True
    max_items: int = Field(200, ge=1)


class ExternalDepsRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: ExternalDepsOptions = Field(default_factory=ExternalDepsOptions)


class ExternalDepsObject(BaseModel):
    name: str
    type: str


class ExternalDepsSummary(BaseModel):
    has_external_deps: bool
    linked_server_count: int
    cross_db_count: int
    remote_exec_count: int
    openquery_count: int
    opendatasource_count: int


class LinkedServerItem(BaseModel):
    name: str
    signals: list[str]


class CrossDatabaseItem(BaseModel):
    database: str
    schema_: str = Field(..., alias="schema")
    object: str
    kind: str


class TargetDependencyItem(BaseModel):
    target: str
    kind: str
    signals: list[str]


class OtherDependencyItem(BaseModel):
    id: str
    kind: str
    signals: list[str]


class ExternalDependencies(BaseModel):
    linked_servers: list[LinkedServerItem]
    cross_database: list[CrossDatabaseItem]
    remote_exec: list[TargetDependencyItem]
    openquery: list[TargetDependencyItem]
    opendatasource: list[TargetDependencyItem]
    others: list[OtherDependencyItem]


class ExternalDepsResponse(BaseModel):
    version: str
    object: ExternalDepsObject
    summary: ExternalDepsSummary
    external_dependencies: ExternalDependencies
    signals: list[str]
    errors: list[str]


class ReusabilityOptions(BaseModel):
    max_reason_items: int = Field(20, ge=1)


class ReusabilityRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: ReusabilityOptions = Field(default_factory=ReusabilityOptions)


class ReusabilityObject(BaseModel):
    name: str
    type: str


class ReusabilitySummary(BaseModel):
    score: int
    grade: str
    is_candidate: bool
    candidate_type: str | None


class ReusabilitySignals(BaseModel):
    read_only: bool
    has_writes: bool
    uses_transaction: bool
    has_dynamic_sql: bool
    has_cursor: bool
    uses_temp_objects: bool
    cyclomatic_complexity: int
    table_count: int
    function_call_count: int
    has_try_catch: bool
    error_signaling: list[str]


class ReusabilityReason(BaseModel):
    id: str
    impact: str
    weight: int
    message: str


class ReusabilityRecommendation(BaseModel):
    id: str
    message: str


class ReusabilityResponse(BaseModel):
    version: str
    object: ReusabilityObject
    summary: ReusabilitySummary
    signals: ReusabilitySignals
    reasons: list[ReusabilityReason]
    recommendations: list[ReusabilityRecommendation]
    errors: list[str]


class BusinessRulesOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    max_rules: int = Field(100, ge=1)
    max_templates: int = Field(150, ge=1)


class BusinessRulesRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: BusinessRulesOptions = Field(default_factory=BusinessRulesOptions)


class BusinessRulesObject(BaseModel):
    name: str
    type: str


class BusinessRulesSummary(BaseModel):
    has_rules: bool
    rule_count: int
    template_suggestion_count: int
    truncated: bool


class BusinessRule(BaseModel):
    id: str
    kind: str
    confidence: float
    condition: str
    action: str
    signals: list[str]


class BusinessRuleTemplateSuggestion(BaseModel):
    rule_id: str
    template_id: str
    confidence: float
    rationale: str


class BusinessRulesResponse(BaseModel):
    version: str
    object: BusinessRulesObject
    summary: BusinessRulesSummary
    rules: list[BusinessRule]
    template_suggestions: list[BusinessRuleTemplateSuggestion]
    signals: list[str]
    errors: list[str]


class CallGraphOptions(BaseModel):
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_functions: bool = True
    include_procedures: bool = True
    ignore_dynamic_exec: bool = True
    max_nodes: int = Field(500, ge=1)
    max_edges: int = Field(2000, ge=1)


class CallGraphObject(BaseModel):
    name: str
    type: str
    sql: str


class CallGraphRequest(BaseModel):
    objects: list[CallGraphObject]
    options: CallGraphOptions = Field(default_factory=CallGraphOptions)


class CallGraphSummary(BaseModel):
    object_count: int
    node_count: int
    edge_count: int
    has_cycles: bool
    truncated: bool


class CallGraphNode(BaseModel):
    id: str
    name: str
    type: str


class CallGraphEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    kind: str
    count: int
    signals: list[str]


class CallGraph(BaseModel):
    nodes: list[CallGraphNode]
    edges: list[CallGraphEdge]


class CallGraphTopology(BaseModel):
    roots: list[str]
    leaves: list[str]
    in_degree: dict[str, int]
    out_degree: dict[str, int]


class CallGraphError(BaseModel):
    id: str
    message: str
    object: str | None = None


class CallGraphResponse(BaseModel):
    version: str
    summary: CallGraphSummary
    graph: CallGraph
    topology: CallGraphTopology
    errors: list[CallGraphError]


class MappingStrategyOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    target_style: Literal["rewrite", "call_sp_first"] = "rewrite"
    max_items: int = Field(30, ge=1)


class MappingStrategyRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: MappingStrategyOptions = Field(default_factory=MappingStrategyOptions)


class MappingStrategyObject(BaseModel):
    name: str
    type: str


class MappingStrategySummary(BaseModel):
    approach: str
    confidence: float
    difficulty: str
    is_recommended: bool


class MappingStrategySignals(BaseModel):
    read_only: bool
    has_writes: bool
    writes_kind: list[str]
    uses_transaction: bool
    has_dynamic_sql: bool
    has_cursor: bool
    uses_temp_objects: bool
    has_merge: bool
    has_identity_retrieval: bool
    has_output_clause: bool
    cyclomatic_complexity: int
    table_count: int
    has_try_catch: bool
    error_signaling: list[str]


class StrategyPattern(BaseModel):
    id: str
    message: str


class MappingStrategyPlan(BaseModel):
    migration_path: list[str]
    recommended_patterns: list[StrategyPattern]
    anti_patterns: list[StrategyPattern]


class MapperMethod(BaseModel):
    name: str
    kind: str
    parameter_style: str
    return_style: str


class XmlTemplate(BaseModel):
    statement_tag: str
    skeleton: str
    dynamic_tags: list[str]


class MyBatisMapping(BaseModel):
    mapper_method: MapperMethod
    xml_template: XmlTemplate


class ServicePattern(BaseModel):
    transactional: bool
    exception_mapping: str


class DtoSuggestion(BaseModel):
    id: str
    fields: list[str]
    notes: str


class JavaMapping(BaseModel):
    service_pattern: ServicePattern
    dto_suggestions: list[DtoSuggestion]


class MappingStrategyReason(BaseModel):
    id: str
    weight: int
    message: str


class MappingStrategyRecommendation(BaseModel):
    id: str
    message: str


class MappingStrategyResponse(BaseModel):
    version: str
    object: MappingStrategyObject
    summary: MappingStrategySummary
    signals: MappingStrategySignals
    strategy: MappingStrategyPlan
    mybatis: MyBatisMapping
    java: JavaMapping
    reasons: list[MappingStrategyReason]
    recommendations: list[MappingStrategyRecommendation]
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


@router.post("/external-deps", response_model=ExternalDepsResponse)
def external_deps(request: ExternalDepsRequest) -> ExternalDepsResponse:
    result = analyze_external_dependencies(
        request.sql,
        options={
            "case_insensitive": request.options.case_insensitive,
            "max_items": request.options.max_items,
            "name": request.name,
            "type": request.type,
        },
    )
    return ExternalDepsResponse(**result)


@router.post("/common/reusability", response_model=ReusabilityResponse)
def common_reusability(request: ReusabilityRequest) -> ReusabilityResponse:
    result = evaluate_reusability(
        request.sql,
        max_reason_items=request.options.max_reason_items,
    )
    return ReusabilityResponse(
        version=result["version"],
        object=ReusabilityObject(name=request.name, type=request.type),
        summary=ReusabilitySummary(**result["summary"]),
        signals=ReusabilitySignals(**result["signals"]),
        reasons=[ReusabilityReason(**item) for item in result["reasons"]],
        recommendations=[ReusabilityRecommendation(**item) for item in result["recommendations"]],
        errors=result["errors"],
    )


@router.post("/common/rules-template", response_model=BusinessRulesResponse)
def common_rules_template(request: BusinessRulesRequest) -> BusinessRulesResponse:
    result = analyze_business_rules(
        request.sql,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        max_rules=request.options.max_rules,
        max_templates=request.options.max_templates,
    )
    return BusinessRulesResponse(
        version=result["version"],
        object=BusinessRulesObject(name=request.name, type=request.type),
        summary=BusinessRulesSummary(**result["summary"]),
        rules=[BusinessRule(**item) for item in result["rules"]],
        template_suggestions=[
            BusinessRuleTemplateSuggestion(**item) for item in result["template_suggestions"]
        ],
        signals=result["signals"],
        errors=result["errors"],
    )


@router.post("/common/call-graph", response_model=CallGraphResponse)
def common_call_graph(request: CallGraphRequest) -> CallGraphResponse:
    service_objects = [
        ServiceCallGraphObject(name=obj.name, type=obj.type, sql=obj.sql) for obj in request.objects
    ]
    service_options = ServiceCallGraphOptions(
        case_insensitive=request.options.case_insensitive,
        schema_sensitive=request.options.schema_sensitive,
        include_functions=request.options.include_functions,
        include_procedures=request.options.include_procedures,
        ignore_dynamic_exec=request.options.ignore_dynamic_exec,
        max_nodes=request.options.max_nodes,
        max_edges=request.options.max_edges,
    )
    result = build_call_graph(service_objects, service_options)
    return CallGraphResponse(**result)


@router.post("/migration/mapping-strategy", response_model=MappingStrategyResponse)
def migration_mapping_strategy(request: MappingStrategyRequest) -> MappingStrategyResponse:
    result = recommend_mapping_strategy(
        request.sql,
        request.type,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        target_style=request.options.target_style,
        max_items=request.options.max_items,
    )
    return MappingStrategyResponse(
        version=result["version"],
        object=MappingStrategyObject(name=request.name, type=request.type),
        summary=MappingStrategySummary(**result["summary"]),
        signals=MappingStrategySignals(**result["signals"]),
        strategy=MappingStrategyPlan(
            migration_path=result["strategy"]["migration_path"],
            recommended_patterns=[
                StrategyPattern(**item) for item in result["strategy"]["recommended_patterns"]
            ],
            anti_patterns=[StrategyPattern(**item) for item in result["strategy"]["anti_patterns"]],
        ),
        mybatis=MyBatisMapping(
            mapper_method=MapperMethod(**result["mybatis"]["mapper_method"]),
            xml_template=XmlTemplate(**result["mybatis"]["xml_template"]),
        ),
        java=JavaMapping(
            service_pattern=ServicePattern(**result["java"]["service_pattern"]),
            dto_suggestions=[DtoSuggestion(**item) for item in result["java"]["dto_suggestions"]],
        ),
        reasons=[MappingStrategyReason(**item) for item in result["reasons"]],
        recommendations=[
            MappingStrategyRecommendation(**item) for item in result["recommendations"]
        ],
        errors=result["errors"],
    )


def _infer_target_type(target: str, target_type: str | None) -> str:
    if target_type:
        return target_type.lower()
    if "(" in target:
        return "function"
    return "procedure"

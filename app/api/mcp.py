# [파일 설명]
# - 목적: MCP API 라우트를 정의하고 요청/응답 모델을 제공한다.
# - 제공 기능: 분석, 표준화, 호출 그래프 등 여러 POST 엔드포인트를 제공한다.
# - 입력/출력: Pydantic 모델로 요청을 수신하고 표준화된 응답 구조를 반환한다.
# - 주의 사항: 원문 SQL은 로깅/응답에 직접 노출하지 않는 흐름을 유지한다.
# - 연관 모듈: app.services.* 분석/추천 서비스들과 연결된다.
from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

from app.services.rag_lexical import (
    build_index,
    build_pattern_recommendations,
    build_snippet,
    extract_query_terms,
    load_documents,
    search,
)
from app.services.safe_sql import summarize_sql
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
from app.services.tsql_db_dependency import analyze_db_dependency
from app.services.tsql_external_deps import analyze_external_dependencies
from app.services.tsql_mapping_strategy import recommend_mapping_strategy
from app.services.tsql_mybatis_difficulty import evaluate_mybatis_difficulty
from app.services.tsql_performance_risk import analyze_performance_risk
from app.services.tsql_reusability import evaluate_reusability
from app.services.tsql_standardization_spec import (
    Options as ServiceStandardizationOptions,
)
from app.services.tsql_standardization_spec import build_standardization_spec
from app.services.tsql_tx_boundary import recommend_transaction_boundary

logger = logging.getLogger(__name__)

router = APIRouter()


# [클래스 설명]
# - 역할: AnalyzeRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class AnalyzeRequest(BaseModel):
    sql: str = Field(..., min_length=1)
    dialect: str = "tsql"


# [클래스 설명]
# - 역할: References Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class References(BaseModel):
    tables: list[str]
    functions: list[str]


# [클래스 설명]
# - 역할: TransactionSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: ImpactItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ImpactItem(BaseModel):
    id: str
    category: str
    severity: str
    title: str
    signals: list[str]
    details: str


# [클래스 설명]
# - 역할: MigrationImpacts Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MigrationImpacts(BaseModel):
    has_impact: bool
    items: list[ImpactItem]


# [클래스 설명]
# - 역할: ControlFlowSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: ControlFlowNode Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ControlFlowNode(BaseModel):
    id: str
    type: str
    label: str


# [클래스 설명]
# - 역할: ControlFlowEdge Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ControlFlowEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    label: str


# [클래스 설명]
# - 역할: ControlFlowGraph Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ControlFlowGraph(BaseModel):
    nodes: list[ControlFlowNode]
    edges: list[ControlFlowEdge]


# [클래스 설명]
# - 역할: ControlFlow Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ControlFlow(BaseModel):
    summary: ControlFlowSummary
    graph: ControlFlowGraph
    signals: list[str]


# [클래스 설명]
# - 역할: DataChangeOperation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DataChangeOperation(BaseModel):
    count: int
    tables: list[str]


# [클래스 설명]
# - 역할: DataChangeOperations Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DataChangeOperations(BaseModel):
    insert: DataChangeOperation
    update: DataChangeOperation
    delete: DataChangeOperation
    merge: DataChangeOperation
    truncate: DataChangeOperation
    select_into: DataChangeOperation


# [클래스 설명]
# - 역할: TableOperation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TableOperation(BaseModel):
    table: str
    ops: list[str]


# [클래스 설명]
# - 역할: DataChanges Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DataChanges(BaseModel):
    has_writes: bool
    operations: DataChangeOperations
    table_operations: list[TableOperation]
    signals: list[str]
    notes: list[str]


# [클래스 설명]
# - 역할: ErrorHandling Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: AnalyzeResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class AnalyzeResponse(BaseModel):
    version: str
    references: References
    transactions: TransactionSummary
    migration_impacts: MigrationImpacts
    control_flow: ControlFlow
    data_changes: DataChanges
    error_handling: ErrorHandling
    errors: list[str]


# [클래스 설명]
# - 역할: StandardizeSpecObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: StandardizeSpecOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    include_sections: list[str] | None = None
    max_items_per_section: int = 50


# [클래스 설명]
# - 역할: StandardizeSpecRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecRequest(BaseModel):
    object: StandardizeSpecObject
    sql: str | None = None
    inputs: dict[str, dict[str, object]] | None = None
    options: StandardizeSpecOptions = Field(default_factory=StandardizeSpecOptions)

    # [함수 설명]
    # - 목적: validate_payload 처리 로직을 수행한다.
    # - 입력: self
    # - 출력: 구조화된 dict 결과를 반환한다.
    # - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
    # - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
    # - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
    @model_validator(mode="after")
    def validate_payload(self) -> StandardizeSpecRequest:
        if self.sql and self.inputs:
            raise ValueError("Provide either sql or inputs, not both.")
        if not self.sql and not self.inputs:
            raise ValueError("Provide sql or inputs.")
        return self


# [클래스 설명]
# - 역할: StandardizeSpecObjectResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecObjectResponse(BaseModel):
    name: str
    type: str
    normalized: str


# [클래스 설명]
# - 역할: StandardizeSpecSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecSummary(BaseModel):
    one_liner: str
    risk_level: str
    difficulty_level: str


# [클래스 설명]
# - 역할: StandardizeSpecTemplate Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecTemplate(BaseModel):
    id: str
    source: str
    confidence: float


# [클래스 설명]
# - 역할: StandardizeSpecRule Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecRule(BaseModel):
    id: str
    kind: str
    condition: str
    action: str


# [클래스 설명]
# - 역할: StandardizeSpecDependencies Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecDependencies(BaseModel):
    tables: list[str]
    functions: list[str]
    cross_db: list[str]
    linked_servers: list[str]


# [클래스 설명]
# - 역할: StandardizeSpecTransactions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecTransactions(BaseModel):
    recommended_boundary: str | None
    propagation: str | None
    isolation_level: str | None


# [클래스 설명]
# - 역할: StandardizeSpecMyBatis Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecMyBatis(BaseModel):
    approach: str
    difficulty_score: int | None


# [클래스 설명]
# - 역할: StandardizeSpecRisks Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecRisks(BaseModel):
    migration_impacts: list[str]
    performance: list[str]
    db_dependency: list[str]


# [클래스 설명]
# - 역할: StandardizeSpecRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: StandardizeSpecEvidence Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecEvidence(BaseModel):
    signals: dict[str, object]


# [클래스 설명]
# - 역할: StandardizeSpecPayload Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecPayload(BaseModel):
    tags: list[str]
    summary: StandardizeSpecSummary
    templates: list[StandardizeSpecTemplate]
    rules: list[StandardizeSpecRule]
    dependencies: StandardizeSpecDependencies
    transactions: StandardizeSpecTransactions
    mybatis: StandardizeSpecMyBatis
    risks: StandardizeSpecRisks
    recommendations: list[StandardizeSpecRecommendation]
    evidence: StandardizeSpecEvidence


# [클래스 설명]
# - 역할: StandardizeSpecResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecResponse(BaseModel):
    version: str
    object: StandardizeSpecObjectResponse
    spec: StandardizeSpecPayload
    errors: list[str]


# [클래스 설명]
# - 역할: StandardizeSpecWithEvidenceOptions 데이터 모델/구성 요소을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecWithEvidenceOptions(StandardizeSpecOptions):
    docs_dir: str = "data/standard_docs"
    top_k: int = 5
    max_snippet_chars: int = 280


# [클래스 설명]
# - 역할: StandardizeSpecWithEvidenceRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecWithEvidenceRequest(BaseModel):
    object: StandardizeSpecObject
    sql: str
    options: StandardizeSpecWithEvidenceOptions = Field(
        default_factory=StandardizeSpecWithEvidenceOptions
    )


# [클래스 설명]
# - 역할: StandardizeSpecEvidenceDocument Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecEvidenceDocument(BaseModel):
    doc_id: str
    title: str
    source: str
    score: float
    snippet: str


# [클래스 설명]
# - 역할: StandardizeSpecPatternRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecPatternRecommendation(BaseModel):
    id: str
    message: str
    source_doc_id: str | None


# [클래스 설명]
# - 역할: StandardizeSpecWithEvidencePayload Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecWithEvidencePayload(BaseModel):
    query_terms: list[str]
    documents: list[StandardizeSpecEvidenceDocument]
    pattern_recommendations: list[StandardizeSpecPatternRecommendation]


# [클래스 설명]
# - 역할: StandardizeSpecWithEvidenceResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StandardizeSpecWithEvidenceResponse(BaseModel):
    version: str
    object: StandardizeSpecObjectResponse
    spec: StandardizeSpecPayload
    evidence: StandardizeSpecWithEvidencePayload
    errors: list[str]


# [클래스 설명]
# - 역할: CallersOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersOptions(BaseModel):
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_self: bool = False


# [클래스 설명]
# - 역할: CallersObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersObject(BaseModel):
    name: str
    type: str
    sql: str


# [클래스 설명]
# - 역할: CallersRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersRequest(BaseModel):
    target: str
    target_type: str | None = None
    objects: list[CallersObject]
    options: CallersOptions = Field(default_factory=CallersOptions)


# [클래스 설명]
# - 역할: CallersTarget Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersTarget(BaseModel):
    name: str
    type: str
    normalized: str


# [클래스 설명]
# - 역할: CallersSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersSummary(BaseModel):
    has_callers: bool
    caller_count: int
    total_calls: int


# [클래스 설명]
# - 역할: CallerResult Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallerResult(BaseModel):
    name: str
    type: str
    call_count: int
    call_kinds: list[str]
    signals: list[str]


# [클래스 설명]
# - 역할: CallersResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallersResponse(BaseModel):
    version: str
    target: CallersTarget
    summary: CallersSummary
    callers: list[CallerResult]
    errors: list[str]


# [클래스 설명]
# - 역할: ExternalDepsOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDepsOptions(BaseModel):
    case_insensitive: bool = True
    max_items: int = Field(200, ge=1)


# [클래스 설명]
# - 역할: ExternalDepsRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDepsRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: ExternalDepsOptions = Field(default_factory=ExternalDepsOptions)


# [클래스 설명]
# - 역할: ExternalDepsObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDepsObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: ExternalDepsSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDepsSummary(BaseModel):
    has_external_deps: bool
    linked_server_count: int
    cross_db_count: int
    remote_exec_count: int
    openquery_count: int
    opendatasource_count: int


# [클래스 설명]
# - 역할: LinkedServerItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class LinkedServerItem(BaseModel):
    name: str
    signals: list[str]


# [클래스 설명]
# - 역할: CrossDatabaseItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CrossDatabaseItem(BaseModel):
    database: str
    schema_: str = Field(..., alias="schema")
    object: str
    kind: str


# [클래스 설명]
# - 역할: TargetDependencyItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TargetDependencyItem(BaseModel):
    target: str
    kind: str
    signals: list[str]


# [클래스 설명]
# - 역할: OtherDependencyItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class OtherDependencyItem(BaseModel):
    id: str
    kind: str
    signals: list[str]


# [클래스 설명]
# - 역할: ExternalDependencies Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDependencies(BaseModel):
    linked_servers: list[LinkedServerItem]
    cross_database: list[CrossDatabaseItem]
    remote_exec: list[TargetDependencyItem]
    openquery: list[TargetDependencyItem]
    opendatasource: list[TargetDependencyItem]
    others: list[OtherDependencyItem]


# [클래스 설명]
# - 역할: ExternalDepsResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ExternalDepsResponse(BaseModel):
    version: str
    object: ExternalDepsObject
    summary: ExternalDepsSummary
    external_dependencies: ExternalDependencies
    signals: list[str]
    errors: list[str]


# [클래스 설명]
# - 역할: ReusabilityOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityOptions(BaseModel):
    max_reason_items: int = Field(20, ge=1)


# [클래스 설명]
# - 역할: ReusabilityRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: ReusabilityOptions = Field(default_factory=ReusabilityOptions)


# [클래스 설명]
# - 역할: ReusabilityObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: ReusabilitySummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilitySummary(BaseModel):
    score: int
    grade: str
    is_candidate: bool
    candidate_type: str | None


# [클래스 설명]
# - 역할: ReusabilitySignals Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: ReusabilityReason Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityReason(BaseModel):
    id: str
    impact: str
    weight: int
    message: str


# [클래스 설명]
# - 역할: ReusabilityRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: ReusabilityResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ReusabilityResponse(BaseModel):
    version: str
    object: ReusabilityObject
    summary: ReusabilitySummary
    signals: ReusabilitySignals
    reasons: list[ReusabilityReason]
    recommendations: list[ReusabilityRecommendation]
    errors: list[str]


# [클래스 설명]
# - 역할: BusinessRulesOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRulesOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    max_rules: int = Field(100, ge=1)
    max_templates: int = Field(150, ge=1)


# [클래스 설명]
# - 역할: BusinessRulesRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRulesRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: BusinessRulesOptions = Field(default_factory=BusinessRulesOptions)


# [클래스 설명]
# - 역할: BusinessRulesObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRulesObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: BusinessRulesSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRulesSummary(BaseModel):
    has_rules: bool
    rule_count: int
    template_suggestion_count: int
    truncated: bool


# [클래스 설명]
# - 역할: BusinessRule Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRule(BaseModel):
    id: str
    kind: str
    confidence: float
    condition: str
    action: str
    signals: list[str]


# [클래스 설명]
# - 역할: BusinessRuleTemplateSuggestion Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRuleTemplateSuggestion(BaseModel):
    rule_id: str
    template_id: str
    confidence: float
    rationale: str


# [클래스 설명]
# - 역할: BusinessRulesResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class BusinessRulesResponse(BaseModel):
    version: str
    object: BusinessRulesObject
    summary: BusinessRulesSummary
    rules: list[BusinessRule]
    template_suggestions: list[BusinessRuleTemplateSuggestion]
    signals: list[str]
    errors: list[str]


# [클래스 설명]
# - 역할: CallGraphOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphOptions(BaseModel):
    case_insensitive: bool = True
    schema_sensitive: bool = False
    include_functions: bool = True
    include_procedures: bool = True
    ignore_dynamic_exec: bool = True
    max_nodes: int = Field(500, ge=1)
    max_edges: int = Field(2000, ge=1)


# [클래스 설명]
# - 역할: CallGraphObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphObject(BaseModel):
    name: str
    type: str
    sql: str


# [클래스 설명]
# - 역할: CallGraphRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphRequest(BaseModel):
    objects: list[CallGraphObject]
    options: CallGraphOptions = Field(default_factory=CallGraphOptions)


# [클래스 설명]
# - 역할: CallGraphSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphSummary(BaseModel):
    object_count: int
    node_count: int
    edge_count: int
    has_cycles: bool
    truncated: bool


# [클래스 설명]
# - 역할: CallGraphNode Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphNode(BaseModel):
    id: str
    name: str
    type: str


# [클래스 설명]
# - 역할: CallGraphEdge Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphEdge(BaseModel):
    from_: str = Field(..., alias="from")
    to: str
    kind: str
    count: int
    signals: list[str]


# [클래스 설명]
# - 역할: CallGraph Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraph(BaseModel):
    nodes: list[CallGraphNode]
    edges: list[CallGraphEdge]


# [클래스 설명]
# - 역할: CallGraphTopology Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphTopology(BaseModel):
    roots: list[str]
    leaves: list[str]
    in_degree: dict[str, int]
    out_degree: dict[str, int]


# [클래스 설명]
# - 역할: CallGraphError Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphError(BaseModel):
    id: str
    message: str
    object: str | None = None


# [클래스 설명]
# - 역할: CallGraphResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class CallGraphResponse(BaseModel):
    version: str
    summary: CallGraphSummary
    graph: CallGraph
    topology: CallGraphTopology
    errors: list[CallGraphError]


# [클래스 설명]
# - 역할: MappingStrategyOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    target_style: Literal["rewrite", "call_sp_first"] = "rewrite"
    max_items: int = Field(30, ge=1)


# [클래스 설명]
# - 역할: MappingStrategyRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: MappingStrategyOptions = Field(default_factory=MappingStrategyOptions)


# [클래스 설명]
# - 역할: MappingStrategyObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: MappingStrategySummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategySummary(BaseModel):
    approach: str
    confidence: float
    difficulty: str
    is_recommended: bool


# [클래스 설명]
# - 역할: MappingStrategySignals Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: StrategyPattern Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class StrategyPattern(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: MappingStrategyPlan Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyPlan(BaseModel):
    migration_path: list[str]
    recommended_patterns: list[StrategyPattern]
    anti_patterns: list[StrategyPattern]


# [클래스 설명]
# - 역할: MapperMethod Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MapperMethod(BaseModel):
    name: str
    kind: str
    parameter_style: str
    return_style: str


# [클래스 설명]
# - 역할: XmlTemplate Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class XmlTemplate(BaseModel):
    statement_tag: str
    skeleton: str
    dynamic_tags: list[str]


# [클래스 설명]
# - 역할: MyBatisMapping Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisMapping(BaseModel):
    mapper_method: MapperMethod
    xml_template: XmlTemplate


# [클래스 설명]
# - 역할: ServicePattern Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class ServicePattern(BaseModel):
    transactional: bool
    exception_mapping: str


# [클래스 설명]
# - 역할: DtoSuggestion Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DtoSuggestion(BaseModel):
    id: str
    fields: list[str]
    notes: str


# [클래스 설명]
# - 역할: JavaMapping Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class JavaMapping(BaseModel):
    service_pattern: ServicePattern
    dto_suggestions: list[DtoSuggestion]


# [클래스 설명]
# - 역할: MappingStrategyReason Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyReason(BaseModel):
    id: str
    weight: int
    message: str


# [클래스 설명]
# - 역할: MappingStrategyRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MappingStrategyRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: MappingStrategyResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
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


# [클래스 설명]
# - 역할: TxBoundaryOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundaryOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    prefer_service_layer_tx: bool = True
    max_items: int = Field(30, ge=1)


# [클래스 설명]
# - 역할: TxBoundaryRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundaryRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: TxBoundaryOptions = Field(default_factory=TxBoundaryOptions)


# [클래스 설명]
# - 역할: TxBoundaryObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundaryObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: TxBoundarySummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundarySummary(BaseModel):
    recommended_boundary: str
    transactional: bool
    propagation: str
    isolation_level: str | None
    read_only: bool
    confidence: float


# [클래스 설명]
# - 역할: TxBoundarySignals Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundarySignals(BaseModel):
    has_writes: bool
    write_ops: list[str]
    uses_transaction_in_sql: bool
    begin_count: int
    commit_count: int
    rollback_count: int
    has_try_catch: bool
    xact_abort: str | None
    isolation_level_in_sql: str | None
    has_dynamic_sql: bool
    has_cursor: bool
    uses_temp_objects: bool
    cyclomatic_complexity: int
    error_signaling: list[str]


# [클래스 설명]
# - 역할: TxBoundaryItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundaryItem(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: TxBoundarySnippets Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundarySnippets(BaseModel):
    annotation_example: str
    notes: list[str]


# [클래스 설명]
# - 역할: TxBoundaryResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class TxBoundaryResponse(BaseModel):
    version: str
    object: TxBoundaryObject
    summary: TxBoundarySummary
    signals: TxBoundarySignals
    suggestions: list[TxBoundaryItem]
    anti_patterns: list[TxBoundaryItem]
    java_snippets: TxBoundarySnippets
    errors: list[str]


# [클래스 설명]
# - 역할: MyBatisDifficultyOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    max_reason_items: int = 25


# [클래스 설명]
# - 역할: MyBatisDifficultyRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: MyBatisDifficultyOptions = Field(default_factory=MyBatisDifficultyOptions)


# [클래스 설명]
# - 역할: MyBatisDifficultyObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: MyBatisDifficultySummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultySummary(BaseModel):
    difficulty_score: int
    difficulty_level: str
    estimated_work_units: int
    is_rewrite_recommended: bool
    confidence: float
    truncated: bool


# [클래스 설명]
# - 역할: MyBatisDifficultySignals Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultySignals(BaseModel):
    table_count: int
    function_call_count: int
    has_writes: bool
    write_ops: list[str]
    uses_transaction: bool
    has_dynamic_sql: bool
    has_cursor: bool
    uses_temp_objects: bool
    has_merge: bool
    has_output_clause: bool
    has_identity_retrieval: bool
    has_try_catch: bool
    error_signaling: list[str]
    cyclomatic_complexity: int


# [클래스 설명]
# - 역할: MyBatisDifficultyFactor Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyFactor(BaseModel):
    id: str
    points: int
    message: str


# [클래스 설명]
# - 역할: MyBatisDifficultyRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: MyBatisDifficultyResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class MyBatisDifficultyResponse(BaseModel):
    version: str
    object: MyBatisDifficultyObject
    summary: MyBatisDifficultySummary
    signals: MyBatisDifficultySignals
    factors: list[MyBatisDifficultyFactor]
    recommendations: list[MyBatisDifficultyRecommendation]
    errors: list[str]


# [클래스 설명]
# - 역할: PerformanceRiskOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    max_findings: int = 50


# [클래스 설명]
# - 역할: PerformanceRiskRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: PerformanceRiskOptions = Field(default_factory=PerformanceRiskOptions)


# [클래스 설명]
# - 역할: PerformanceRiskObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: PerformanceRiskSummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskSummary(BaseModel):
    risk_score: int
    risk_level: str
    finding_count: int
    truncated: bool


# [클래스 설명]
# - 역할: PerformanceRiskSignals Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskSignals(BaseModel):
    table_count: int
    has_writes: bool
    uses_transaction: bool
    cyclomatic_complexity: int
    has_cursor: bool
    has_dynamic_sql: bool


# [클래스 설명]
# - 역할: PerformanceRiskFinding Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskFinding(BaseModel):
    id: str
    severity: str
    title: str
    markers: list[str]
    recommendation: str


# [클래스 설명]
# - 역할: PerformanceRiskRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: PerformanceRiskResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class PerformanceRiskResponse(BaseModel):
    version: str
    object: PerformanceRiskObject
    summary: PerformanceRiskSummary
    signals: PerformanceRiskSignals
    findings: list[PerformanceRiskFinding]
    recommendations: list[PerformanceRiskRecommendation]
    errors: list[str]


# [클래스 설명]
# - 역할: DbDependencyOptions Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyOptions(BaseModel):
    dialect: str = "tsql"
    case_insensitive: bool = True
    schema_sensitive: bool = False
    max_items: int = 200


# [클래스 설명]
# - 역할: DbDependencyRequest Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyRequest(BaseModel):
    name: str
    type: str
    sql: str
    options: DbDependencyOptions = Field(default_factory=DbDependencyOptions)


# [클래스 설명]
# - 역할: DbDependencyObject Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyObject(BaseModel):
    name: str
    type: str


# [클래스 설명]
# - 역할: DbDependencySummary Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencySummary(BaseModel):
    dependency_score: int
    dependency_level: str
    truncated: bool


# [클래스 설명]
# - 역할: DbDependencyMetrics Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyMetrics(BaseModel):
    table_count: int
    function_call_count: int
    cross_database_count: int
    linked_server_count: int
    remote_exec_count: int
    openquery_count: int
    opendatasource_count: int
    system_proc_count: int
    xp_cmdshell_count: int
    clr_signal_count: int
    tempdb_pressure_signals: int


# [클래스 설명]
# - 역할: DbDependencyCrossDatabaseItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyCrossDatabaseItem(BaseModel):
    database: str
    schema_: str = Field(..., alias="schema")
    object: str
    kind: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencyLinkedServerItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyLinkedServerItem(BaseModel):
    name: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencyRemoteExecItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyRemoteExecItem(BaseModel):
    target: str
    kind: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencyExternalAccessItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyExternalAccessItem(BaseModel):
    id: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencySystemObjectItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencySystemObjectItem(BaseModel):
    id: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencyTempdbSignalItem Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyTempdbSignalItem(BaseModel):
    id: str
    signals: list[str]


# [클래스 설명]
# - 역할: DbDependencyDependencies Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyDependencies(BaseModel):
    cross_database: list[DbDependencyCrossDatabaseItem]
    linked_servers: list[DbDependencyLinkedServerItem]
    remote_exec: list[DbDependencyRemoteExecItem]
    external_access: list[DbDependencyExternalAccessItem]
    system_objects: list[DbDependencySystemObjectItem]
    tempdb_signals: list[DbDependencyTempdbSignalItem]


# [클래스 설명]
# - 역할: DbDependencyReason Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyReason(BaseModel):
    id: str
    weight: int
    message: str


# [클래스 설명]
# - 역할: DbDependencyRecommendation Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyRecommendation(BaseModel):
    id: str
    message: str


# [클래스 설명]
# - 역할: DbDependencyResponse Pydantic 스키마 모델을 정의한다.
# - 사용 위치: API 요청/응답 또는 서비스 내부 구조에서 사용된다.
# - 핵심 동작: 필드 타입과 검증 규칙을 통해 데이터 구조를 고정한다.
# - 제약/주의: 동작 로직보다 스키마 표현에 집중하며 결정론적 직렬화를 전제로 한다.
class DbDependencyResponse(BaseModel):
    version: str
    object: DbDependencyObject
    summary: DbDependencySummary
    metrics: DbDependencyMetrics
    dependencies: DbDependencyDependencies
    reasons: list[DbDependencyReason]
    recommendations: list[DbDependencyRecommendation]
    errors: list[str]


# [함수 설명]
# - 목적: /analyze 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, references, transactions, migration_impacts, control_flow, data_changes, error_handling, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /standardize/spec 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, spec, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/standardize/spec", response_model=StandardizeSpecResponse)
def standardize_spec(request: StandardizeSpecRequest) -> StandardizeSpecResponse:
    options = ServiceStandardizationOptions(
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        include_sections=request.options.include_sections,
        max_items_per_section=request.options.max_items_per_section,
    )
    result = build_standardization_spec(
        request.object.name,
        request.object.type,
        request.sql,
        request.inputs,
        options,
    )
    return StandardizeSpecResponse(**result)


# [함수 설명]
# - 목적: /standardize/spec-with-evidence 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, spec, evidence, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/standardize/spec-with-evidence", response_model=StandardizeSpecWithEvidenceResponse)
def standardize_spec_with_evidence(
    request: StandardizeSpecWithEvidenceRequest,
) -> StandardizeSpecWithEvidenceResponse:
    options = ServiceStandardizationOptions(
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        include_sections=request.options.include_sections,
        max_items_per_section=request.options.max_items_per_section,
    )
    errors: list[str] = []
    try:
        spec_result = build_standardization_spec(
            request.object.name,
            request.object.type,
            request.sql,
            None,
            options,
        )
    except Exception:
        errors.append("SECTION_NOT_AVAILABLE: standardize_spec")
        spec_result = _empty_standardize_spec(
            request.object.name,
            request.object.type,
        )

    object_payload = spec_result.get("object", {})
    spec_payload = spec_result.get("spec", _empty_spec_payload())
    errors.extend(spec_result.get("errors", []))

    summary = summarize_sql(request.sql)
    logger.info(
        "standardize_spec_with_evidence: sql_len=%s sql_hash=%s docs_dir=%s",
        summary["len"],
        summary["sha256_8"],
        request.options.docs_dir,
    )

    documents: list[StandardizeSpecEvidenceDocument] = []
    query_terms = extract_query_terms(spec_payload)
    evidence_errors: list[str] = []
    hits = []
    docs_path = Path(request.options.docs_dir)
    if not docs_path.exists():
        evidence_errors.append(f"DOCS_DIR_NOT_FOUND: {request.options.docs_dir}")
    else:
        chunks = load_documents(request.options.docs_dir)
        if not chunks:
            evidence_errors.append(f"DOCS_EMPTY: {request.options.docs_dir}")
        else:
            logger.info(
                "standardize_spec_with_evidence: indexed_chunks=%s",
                len(chunks),
            )
            index = build_index(chunks, case_insensitive=request.options.case_insensitive)
            query = " ".join(query_terms)
            hits = search(index, query, request.options.top_k)
            for hit in hits:
                snippet, truncated = build_snippet(hit.text, request.options.max_snippet_chars)
                documents.append(
                    StandardizeSpecEvidenceDocument(
                        doc_id=hit.doc_id,
                        title=hit.title,
                        source=hit.source,
                        score=round(hit.score, 6),
                        snippet=snippet,
                    )
                )
                if truncated:
                    evidence_errors.append(f"SNIPPET_TRUNCATED: {hit.doc_id}")

    if not query_terms:
        evidence_errors.append("QUERY_TERMS_EMPTY")

    pattern_recommendations = build_pattern_recommendations(spec_payload, hits)
    errors.extend(evidence_errors)

    return StandardizeSpecWithEvidenceResponse(
        version="5.2.0",
        object=StandardizeSpecObjectResponse(
            name=object_payload.get("name", request.object.name),
            type=object_payload.get("type", request.object.type),
            normalized=object_payload.get(
                "normalized", _normalize_object_name(request.object.name)
            ),
        ),
        spec=StandardizeSpecPayload(**spec_payload),
        evidence=StandardizeSpecWithEvidencePayload(
            query_terms=query_terms,
            documents=documents,
            pattern_recommendations=[
                StandardizeSpecPatternRecommendation(**item) for item in pattern_recommendations
            ],
        ),
        errors=sorted(set(errors)),
    )


# [함수 설명]
# - 목적: /callers 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, target, summary, callers, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /external-deps 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, external_dependencies, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /common/reusability 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, reasons, recommendations, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /common/rules-template 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, rules, template_suggestions, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /common/call-graph 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, summary, graph, topology, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /migration/mapping-strategy 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, strategy, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
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


# [함수 설명]
# - 목적: /migration/mybatis-difficulty 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, factors, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/migration/mybatis-difficulty", response_model=MyBatisDifficultyResponse)
def migration_mybatis_difficulty(
    request: MyBatisDifficultyRequest,
) -> MyBatisDifficultyResponse:
    result = evaluate_mybatis_difficulty(
        request.sql,
        request.type,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        max_reason_items=request.options.max_reason_items,
    )
    return MyBatisDifficultyResponse(
        version=result["version"],
        object=MyBatisDifficultyObject(name=request.name, type=request.type),
        summary=MyBatisDifficultySummary(**result["summary"]),
        signals=MyBatisDifficultySignals(**result["signals"]),
        factors=[MyBatisDifficultyFactor(**item) for item in result["factors"]],
        recommendations=[
            MyBatisDifficultyRecommendation(**item) for item in result["recommendations"]
        ],
        errors=result["errors"],
    )


# [함수 설명]
# - 목적: /migration/transaction-boundary 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, suggestions, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/migration/transaction-boundary", response_model=TxBoundaryResponse)
def migration_transaction_boundary(request: TxBoundaryRequest) -> TxBoundaryResponse:
    result = recommend_transaction_boundary(
        request.sql,
        request.type,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        prefer_service_layer_tx=request.options.prefer_service_layer_tx,
        max_items=request.options.max_items,
    )
    return TxBoundaryResponse(
        version=result["version"],
        object=TxBoundaryObject(name=request.name, type=request.type),
        summary=TxBoundarySummary(**result["summary"]),
        signals=TxBoundarySignals(**result["signals"]),
        suggestions=[TxBoundaryItem(**item) for item in result["suggestions"]],
        anti_patterns=[TxBoundaryItem(**item) for item in result["anti_patterns"]],
        java_snippets=TxBoundarySnippets(**result["java_snippets"]),
        errors=result["errors"],
    )


# [함수 설명]
# - 목적: /quality/performance-risk 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, findings, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/quality/performance-risk", response_model=PerformanceRiskResponse)
def quality_performance_risk(request: PerformanceRiskRequest) -> PerformanceRiskResponse:
    result = analyze_performance_risk(
        request.sql,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        max_findings=request.options.max_findings,
    )
    return PerformanceRiskResponse(
        version=result["version"],
        object=PerformanceRiskObject(name=request.name, type=request.type),
        summary=PerformanceRiskSummary(**result["summary"]),
        signals=PerformanceRiskSignals(**result["signals"]),
        findings=[PerformanceRiskFinding(**item) for item in result["findings"]],
        recommendations=[
            PerformanceRiskRecommendation(**item) for item in result["recommendations"]
        ],
        errors=result["errors"],
    )


# [함수 설명]
# - 목적: /quality/db-dependency 엔드포인트 요청을 처리한다.
# - 입력: 요청 모델과 옵션을 수신하여 분석/추천을 수행한다.
# - 출력: 응답 모델의 주요 필드는 version, object, summary, metrics, errors이다.
# - 에러 처리: 서비스 오류는 errors 목록에 기록하고 가능한 결과를 반환한다.
# - 결정론: 리스트 결과는 정렬/캡 정책을 통해 안정적으로 반환되도록 한다.
# - 보안: 원문 SQL은 로그에 요약 정보로만 기록한다.
@router.post("/quality/db-dependency", response_model=DbDependencyResponse)
def quality_db_dependency(request: DbDependencyRequest) -> DbDependencyResponse:
    result = analyze_db_dependency(
        request.sql,
        dialect=request.options.dialect,
        case_insensitive=request.options.case_insensitive,
        schema_sensitive=request.options.schema_sensitive,
        max_items=request.options.max_items,
    )
    return DbDependencyResponse(
        version=result["version"],
        object=DbDependencyObject(name=request.name, type=request.type),
        summary=DbDependencySummary(**result["summary"]),
        metrics=DbDependencyMetrics(**result["metrics"]),
        dependencies=DbDependencyDependencies(
            cross_database=[
                DbDependencyCrossDatabaseItem(**item)
                for item in result["dependencies"]["cross_database"]
            ],
            linked_servers=[
                DbDependencyLinkedServerItem(**item)
                for item in result["dependencies"]["linked_servers"]
            ],
            remote_exec=[
                DbDependencyRemoteExecItem(**item) for item in result["dependencies"]["remote_exec"]
            ],
            external_access=[
                DbDependencyExternalAccessItem(**item)
                for item in result["dependencies"]["external_access"]
            ],
            system_objects=[
                DbDependencySystemObjectItem(**item)
                for item in result["dependencies"]["system_objects"]
            ],
            tempdb_signals=[
                DbDependencyTempdbSignalItem(**item)
                for item in result["dependencies"]["tempdb_signals"]
            ],
        ),
        reasons=[DbDependencyReason(**item) for item in result["reasons"]],
        recommendations=[DbDependencyRecommendation(**item) for item in result["recommendations"]],
        errors=result["errors"],
    )


# [함수 설명]
# - 목적: _empty_standardize_spec 처리 로직을 수행한다.
# - 입력: name: str, obj_type: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _empty_standardize_spec(name: str, obj_type: str) -> dict[str, object]:
    return {
        "version": "5.1.0",
        "object": {"name": name, "type": obj_type, "normalized": _normalize_object_name(name)},
        "spec": _empty_spec_payload(),
        "errors": ["SECTION_NOT_AVAILABLE: standardize_spec"],
    }


# [함수 설명]
# - 목적: _empty_spec_payload 처리 로직을 수행한다.
# - 입력: 함수 시그니처 인자
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _empty_spec_payload() -> dict[str, object]:
    return {
        "tags": [],
        "summary": {
            "one_liner": "Spec unavailable.",
            "risk_level": "unknown",
            "difficulty_level": "unknown",
        },
        "templates": [],
        "rules": [],
        "dependencies": {"tables": [], "functions": [], "cross_db": [], "linked_servers": []},
        "transactions": {
            "recommended_boundary": None,
            "propagation": None,
            "isolation_level": None,
        },
        "mybatis": {"approach": "unknown", "difficulty_score": None},
        "risks": {"migration_impacts": [], "performance": [], "db_dependency": []},
        "recommendations": [],
        "evidence": {"signals": {}},
    }


# [함수 설명]
# - 목적: _normalize_object_name 처리 로직을 수행한다.
# - 입력: name: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _normalize_object_name(name: str) -> str:
    return name.replace("[", "").replace("]", "").strip().lower()


# [함수 설명]
# - 목적: _infer_target_type 처리 로직을 수행한다.
# - 입력: target: str, target_type: str | None
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def _infer_target_type(target: str, target_type: str | None) -> str:
    if target_type:
        return target_type.lower()
    if "(" in target:
        return "function"
    return "procedure"

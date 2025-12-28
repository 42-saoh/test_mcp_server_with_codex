## API / Code Specification

### 이 스펙을 최신으로 유지하는 방법 (수동 체크리스트)
- [ ] `app/main.py`, `app/api/mcp.py`의 라우트/모델 변경 여부를 확인한다.
- [ ] `app/services/*`에서 출력 스키마/정렬/트렁케이션 규칙 변경 여부를 확인한다.
- [ ] `tests/` 및 `app/tests/`의 신규/변경 테스트가 있으면 대응 섹션을 업데이트한다.
- [ ] 새 옵션 필드(기본값/제약)가 추가되면 **요청 스키마 표**와 **Data Models** 섹션을 갱신한다.
- [ ] 본 스펙은 **네트워크 접속 없이** 로컬 코드만을 기준으로 갱신한다.

### API 스펙 공통 규칙
- **엔트리포인트**: `app.main:app` (FastAPI)
- **보안/안전**
  - 응답에는 **원문 SQL을 포함하지 않는다**.
  - 로그에도 원문 SQL을 남기지 않으며, 길이/해시 요약(`len`, `sha256_8`)만 기록한다.
- **결정론**
  - 동일 입력에 대해 동일한 출력(정렬/중복 제거/캡 제한)을 보장한다.
  - 정렬 규칙: `_sorted_unique`, `sorted(...)`, 안정적 정렬 키(예: 이름 + 카운트) 사용.
- **에러 표현 방식**
  - 대부분의 엔드포인트는 `errors: list[str]` 또는 구조화된 `errors` 목록을 반환한다.
  - 일부 엔드포인트는 `notes`를 통해 추론/제한 사항을 보완 설명한다.

---

## API 상세

### Health

#### `GET /health`
- **목적**: 서버 상태 확인. 항상 동일한 상태 응답을 반환한다.
- **요청**: 없음 (바디 없음)
- **응답 스키마**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| status | string | required | "ok" | 서버 상태 | 항상 `"ok"` |

- **결정론**: 항상 동일한 `{ "status": "ok" }` 반환.
- **예시 응답**

```json
{"status": "ok"}
```

---

### Feature 1.x — `/mcp/analyze`

#### `POST /mcp/analyze`
- **목적**: T-SQL SP/FN의 참조, 트랜잭션, 마이그레이션 영향, 제어 흐름, 데이터 변경, 오류 처리 패턴을 **통합 분석**한다. SQL 파서를 우선 사용하며, 파서 실패 시 정규식 기반 fallback을 사용한다. 모든 리스트형 결과는 정렬/중복 제거를 통해 결정론적으로 제공된다.
- **요청 스키마 (AnalyzeRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| sql | string | required | - | 분석 대상 SQL | `min_length=1` |
| dialect | string | optional | "tsql" | 파서 dialect | 기본값 `"tsql"` |

- **응답 스키마 (AnalyzeResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | 현재 `"0.6"` |
| references | object | required | 참조 테이블/함수 | `References` 모델 참조 |
| transactions | object | required | 트랜잭션 요약 | `TransactionSummary` 모델 참조 |
| migration_impacts | object | required | 마이그레이션 영향 요약 | `MigrationImpacts` 모델 참조 |
| control_flow | object | required | 제어 흐름 요약/그래프 | `ControlFlow` 모델 참조 |
| data_changes | object | required | 데이터 변경 요약 | `DataChanges` 모델 참조 |
| error_handling | object | required | 오류 처리 요약 | `ErrorHandling` 모델 참조 |
| errors | array[string] | required | 오류 목록 | 파서 실패/그래프 제한 등 |

- **결정론/트렁케이션 규칙**
  - 참조 리스트는 정렬/중복 제거됨.
  - `control_flow.graph`는 `CONTROL_FLOW_NODE_LIMIT(200)`, `CONTROL_FLOW_EDGE_LIMIT(400)` 초과 시 `errors`에 `control_flow_graph_truncated`를 기록.
  - `data_changes.table_operations`는 테이블명 기준 정렬.
- **안전 규칙**: 원문 SQL 미포함(응답/로그 모두). 로그는 `summarize_sql` 요약만 기록.
- **예시 요청/응답**

```json
{"sql": "CREATE PROCEDURE dbo.usp_demo AS SELECT 1", "dialect": "tsql"}
```

```json
{
  "version": "0.6",
  "references": {"tables": [], "functions": []},
  "transactions": {
    "uses_transaction": false,
    "begin_count": 0,
    "commit_count": 0,
    "rollback_count": 0,
    "savepoint_count": 0,
    "has_try_catch": false,
    "xact_abort": null,
    "isolation_level": null,
    "signals": []
  },
  "migration_impacts": {"has_impact": false, "items": []},
  "control_flow": {
    "summary": {
      "has_branching": false,
      "has_loops": false,
      "has_try_catch": false,
      "has_goto": false,
      "has_return": false,
      "branch_count": 0,
      "loop_count": 0,
      "return_count": 0,
      "goto_count": 0,
      "max_nesting_depth": 0,
      "cyclomatic_complexity": 1
    },
    "graph": {"nodes": [], "edges": []},
    "signals": []
  },
  "data_changes": {
    "has_writes": false,
    "operations": {
      "insert": {"count": 0, "tables": []},
      "update": {"count": 0, "tables": []},
      "delete": {"count": 0, "tables": []},
      "merge": {"count": 0, "tables": []},
      "truncate": {"count": 0, "tables": []},
      "select_into": {"count": 0, "tables": []}
    },
    "table_operations": [],
    "signals": [],
    "notes": []
  },
  "error_handling": {
    "has_try_catch": false,
    "try_count": 0,
    "catch_count": 0,
    "uses_throw": false,
    "throw_count": 0,
    "uses_raiserror": false,
    "raiserror_count": 0,
    "uses_at_at_error": false,
    "at_at_error_count": 0,
    "uses_error_functions": [],
    "uses_print": false,
    "print_count": 0,
    "uses_return": false,
    "return_count": 0,
    "return_values": [],
    "uses_output_error_params": false,
    "output_error_params": [],
    "signals": [],
    "notes": []
  },
  "errors": []
}
```

---

### Feature 2.x — `/mcp/common/*` (공통 분석)

#### `POST /mcp/callers`
- **경로 특이사항**: `/mcp/common/*`가 아닌 **`/mcp/callers`** 경로에 구현됨.
- **목적**: 대상 SP/FN을 호출하는 다른 객체 목록 및 호출 수를 분석한다. 요청 객체 수/총 SQL 길이 제한을 적용한다.
- **요청 스키마 (CallersRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| target | string | required | - | 호출 대상 이름 | 예: `dbo.usp_target` |
| target_type | string | optional | null | 대상 유형 | 미지정 시 이름에 `(` 포함 여부로 추론 |
| objects | array[CallersObject] | required | - | 검색 대상 객체 목록 | 최대 500개 처리 |
| options | CallersOptions | optional | defaults | 비교/검색 옵션 | `case_insensitive=true` 등 |

- **응답 스키마 (CallersResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"2.1.0"` |
| target | object | required | 대상 정보 | `CallersTarget` 모델 참조 |
| summary | object | required | 요약 | `CallersSummary` 모델 참조 |
| callers | array[CallerResult] | required | 호출자 목록 | 호출 수/이름 기준 정렬 |
| errors | array[string] | required | 제한/트렁케이션 에러 | SQL 길이 제한 등 |

- **결정론/트렁케이션 규칙**
  - 처리 객체 수 제한: `MAX_OBJECTS=500`.
  - 총 SQL 길이 제한: `MAX_TOTAL_SQL_LENGTH=1_000_000`.
  - `callers`는 `call_count` 내림차순, 이름 소문자 기준 정렬.
  - `signals`는 최대 10개까지 제한.

#### `POST /mcp/external-deps`
- **경로 특이사항**: `/mcp/common/*`가 아닌 **`/mcp/external-deps`** 경로에 구현됨.
- **목적**: 링크드 서버/크로스DB/원격 실행 등 외부 의존성을 정규식 기반으로 탐지한다. 문자열/주석 마스킹 후 탐지한다.
- **요청 스키마 (ExternalDepsRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | ExternalDepsOptions | optional | defaults | 탐지 옵션 | `max_items=200` |

- **응답 스키마 (ExternalDepsResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"2.2.0"` |
| object | object | required | 대상 정보 | `ExternalDepsObject` 모델 참조 |
| summary | object | required | 요약 | `ExternalDepsSummary` 모델 참조 |
| external_dependencies | object | required | 의존성 상세 | `ExternalDependencies` 모델 참조 |
| signals | array[string] | required | 탐지 신호 | 정렬/중복 제거 |
| errors | array[string] | required | 트렁케이션/제한 | `max_items` 초과 등 |

- **결정론/트렁케이션 규칙**
  - 의존성 항목은 정렬/중복 제거 후 `max_items` 제한.
  - 제한 발생 시 `errors`에 `max_items_exceeded: ...` 기록.

#### `POST /mcp/common/reusability`
- **목적**: 재사용성 평가(스코어/등급/사유/권장사항). 제어 흐름/트랜잭션/에러 신호 등을 종합한다.
- **요청 스키마 (ReusabilityRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | ReusabilityOptions | optional | defaults | 최대 사유 항목 | `max_reason_items=20` |

- **응답 스키마 (ReusabilityResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"1.2.0"` |
| object | object | required | 대상 정보 | `ReusabilityObject` 모델 참조 |
| summary | object | required | 요약 | `ReusabilitySummary` 모델 참조 |
| signals | object | required | 판단 신호 | `ReusabilitySignals` 모델 참조 |
| reasons | array[ReusabilityReason] | required | 사유 | `max_reason_items` 제한 |
| recommendations | array[ReusabilityRecommendation] | required | 권장사항 | 제한 및 정렬 적용 |
| errors | array[string] | required | 에러/제한 |  |

#### `POST /mcp/common/rules-template`
- **목적**: SQL에서 비즈니스 규칙을 추출하고 템플릿 매핑 제안을 제공한다. 규칙/템플릿 수는 제한되며, 제한 발생 시 `summary.truncated` 및 `errors`에 기록된다.
- **요청 스키마 (BusinessRulesRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | BusinessRulesOptions | optional | defaults | 규칙/템플릿 제한 | `max_rules=100`, `max_templates=150` |

- **응답 스키마 (BusinessRulesResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"2.3.0"` |
| object | object | required | 대상 정보 | `BusinessRulesObject` 모델 참조 |
| summary | object | required | 요약 | `BusinessRulesSummary` 모델 참조 |
| rules | array[BusinessRule] | required | 규칙 목록 | 정렬/캡 적용 |
| template_suggestions | array[BusinessRuleTemplateSuggestion] | required | 템플릿 제안 | 정렬/캡 적용 |
| signals | array[string] | required | 신호 | 중복 제거 |
| errors | array[string] | required | 제한/추론 에러 | 트렁케이션 포함 |

#### `POST /mcp/common/call-graph`
- **목적**: 객체 간 호출 그래프를 생성한다. 노드/엣지 수 제한을 적용한다.
- **요청 스키마 (CallGraphRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| objects | array[CallGraphObject] | required | - | 분석 대상 객체 목록 |  |
| options | CallGraphOptions | optional | defaults | 필터/제한 옵션 | `max_nodes=500`, `max_edges=2000` |

- **응답 스키마 (CallGraphResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"2.4.0"` |
| summary | object | required | 요약 | `CallGraphSummary` 모델 참조 |
| graph | object | required | 그래프 | `CallGraph` 모델 참조 |
| topology | object | required | 위상 정보 | `CallGraphTopology` 모델 참조 |
| errors | array[CallGraphError] | required | 그래프 에러 | 노드/엣지 제한 등 |

- **결정론/트렁케이션 규칙**
  - 노드/엣지 수 제한(`max_nodes`, `max_edges`)을 초과하면 `summary.truncated`와 `errors`에 기록.

- **미구현 엔드포인트**: 없음.

---

### Feature 3.x — `/mcp/migration/*`

#### `POST /mcp/migration/mapping-strategy`
- **목적**: Java + MyBatis 매핑 전략을 결정론적으로 추천한다. 기본은 `rewrite`, 위험 신호가 높을 때 `call_sp_first`를 추천한다.
- **요청 스키마 (MappingStrategyRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | MappingStrategyOptions | optional | defaults | 전략/캡 옵션 | `target_style="rewrite"`, `max_items=30` |

- **응답 스키마 (MappingStrategyResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"3.1.0"` |
| object | object | required | 대상 정보 | `MappingStrategyObject` 모델 참조 |
| summary | object | required | 전략 요약 | `MappingStrategySummary` 모델 참조 |
| signals | object | required | 판단 신호 | `MappingStrategySignals` 모델 참조 |
| strategy | object | required | 패턴/경로 | `MappingStrategyPlan` 모델 참조 |
| mybatis | object | required | MyBatis 제안 | `MyBatisMapping` 모델 참조 |
| java | object | required | Java 제안 | `JavaMapping` 모델 참조 |
| reasons | array[MappingStrategyReason] | required | 사유 | `max_items` 제한 |
| recommendations | array[MappingStrategyRecommendation] | required | 권장사항 | `max_items` 제한 |
| errors | array[string] | required | 제한/에러 | `max_items_exceeded` 등 |

#### `POST /mcp/migration/mybatis-difficulty`
- **목적**: MyBatis 변환 난이도를 점수화하고 요인/권장사항을 제공한다.
- **요청 스키마 (MyBatisDifficultyRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | MyBatisDifficultyOptions | optional | defaults | 제한 옵션 | `max_reason_items=25` |

- **응답 스키마 (MyBatisDifficultyResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"3.3.0"` |
| object | object | required | 대상 정보 | `MyBatisDifficultyObject` 모델 참조 |
| summary | object | required | 요약 | `MyBatisDifficultySummary` 모델 참조 (`truncated` 포함) |
| signals | object | required | 신호 | `MyBatisDifficultySignals` 모델 참조 |
| factors | array[MyBatisDifficultyFactor] | required | 난이도 요인 | `max_reason_items` 제한 |
| recommendations | array[MyBatisDifficultyRecommendation] | required | 권장사항 | 제한 적용 |
| errors | array[string] | required | 제한/에러 | `max_reason_items_exceeded` 등 |

#### `POST /mcp/migration/transaction-boundary`
- **목적**: 트랜잭션 경계를 추천하고 Java 스니펫을 제공한다.
- **요청 스키마 (TxBoundaryRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | TxBoundaryOptions | optional | defaults | 제한 옵션 | `prefer_service_layer_tx=true`, `max_items=30` |

- **응답 스키마 (TxBoundaryResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"3.2.0"` |
| object | object | required | 대상 정보 | `TxBoundaryObject` 모델 참조 |
| summary | object | required | 요약 | `TxBoundarySummary` 모델 참조 |
| signals | object | required | 신호 | `TxBoundarySignals` 모델 참조 |
| suggestions | array[TxBoundaryItem] | required | 권장 항목 | `max_items` 제한 |
| anti_patterns | array[TxBoundaryItem] | required | 안티 패턴 | `max_items` 제한 |
| java_snippets | object | required | Java 예시 | `TxBoundarySnippets` 모델 참조 |
| errors | array[string] | required | 제한/에러 | `max_items_exceeded` 등 |

- **미구현 엔드포인트**: 없음.

---

### Feature 4.x — `/mcp/quality/*`

#### `POST /mcp/quality/performance-risk`
- **목적**: 성능 리스크를 탐지하고 요약/권장사항을 제공한다.
- **요청 스키마 (PerformanceRiskRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | PerformanceRiskOptions | optional | defaults | 제한 옵션 | `max_findings=50` |

- **응답 스키마 (PerformanceRiskResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"4.1.0"` |
| object | object | required | 대상 정보 | `PerformanceRiskObject` 모델 참조 |
| summary | object | required | 요약 | `PerformanceRiskSummary` 모델 참조 (`truncated` 포함) |
| signals | object | required | 신호 | `PerformanceRiskSignals` 모델 참조 |
| findings | array[PerformanceRiskFinding] | required | 탐지 항목 | `max_findings` 제한 |
| recommendations | array[PerformanceRiskRecommendation] | required | 권장사항 | 정렬/중복 제거 |
| errors | array[string] | required | 제한/에러 | `findings_truncated` 등 |

#### `POST /mcp/quality/db-dependency`
- **목적**: DB 의존도(크로스DB/링크드서버/시스템 객체/외부 접근 등)를 정량화한다.
- **요청 스키마 (DbDependencyRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | 분석 대상 SQL |  |
| options | DbDependencyOptions | optional | defaults | 제한 옵션 | `max_items=200` |

- **응답 스키마 (DbDependencyResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"4.2.0"` |
| object | object | required | 대상 정보 | `DbDependencyObject` 모델 참조 |
| summary | object | required | 요약 | `DbDependencySummary` 모델 참조 (`truncated` 포함) |
| metrics | object | required | 지표 | `DbDependencyMetrics` 모델 참조 |
| dependencies | object | required | 의존성 상세 | `DbDependencyDependencies` 모델 참조 |
| reasons | array[DbDependencyReason] | required | 사유 | 정렬/중복 제거 |
| recommendations | array[DbDependencyRecommendation] | required | 권장사항 | 정렬/중복 제거 |
| errors | array[string] | required | 제한/에러 | `dependency_items_truncated` 등 |

- **미구현 엔드포인트**: 없음.

---

### Feature 5.x — `/mcp/standardize/*`

#### `POST /mcp/standardize/spec`
- **목적**: 표준화 스펙(태그/요약/규칙/리스크 등)을 생성한다. `sql` 또는 `inputs` 중 하나만 제공해야 한다.
- **요청 스키마 (StandardizeSpecRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| object | StandardizeSpecObject | required | - | 대상 객체 | `name`, `type` 포함 |
| sql | string | optional | null | 분석 SQL | `sql`과 `inputs` 동시 제공 금지 |
| inputs | object | optional | null | 사전 계산 입력 | `sql` 없을 때 사용 |
| options | StandardizeSpecOptions | optional | defaults | 섹션/캡 옵션 | `max_items_per_section=50` |

- **응답 스키마 (StandardizeSpecResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"5.1.0"` |
| object | object | required | 대상 정보 | `StandardizeSpecObjectResponse` 모델 참조 |
| spec | object | required | 스펙 본문 | `StandardizeSpecPayload` 모델 참조 |
| errors | array[string] | required | 에러/제한 |  |

#### `POST /mcp/standardize/spec-with-evidence`
- **목적**: 표준화 스펙 + 근거 문서(RAG) 결과를 제공한다. 문서 디렉터리가 없으면 오류를 반환하되 스펙은 가능한 한 유지한다.
- **요청 스키마 (StandardizeSpecWithEvidenceRequest)**

| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| object | StandardizeSpecObject | required | - | 대상 객체 |  |
| sql | string | required | - | 분석 SQL |  |
| options | StandardizeSpecWithEvidenceOptions | optional | defaults | 문서 옵션 | `docs_dir="data/standard_docs"`, `top_k=5` |

- **응답 스키마 (StandardizeSpecWithEvidenceResponse)**

| Field | Type | Required | Description | Notes |
| --- | --- | --- | --- | --- |
| version | string | required | 응답 버전 | `"5.2.0"` |
| object | object | required | 대상 정보 | `StandardizeSpecObjectResponse` 모델 참조 |
| spec | object | required | 스펙 본문 | `StandardizeSpecPayload` 모델 참조 |
| evidence | object | required | 근거 문서 | `StandardizeSpecWithEvidencePayload` 모델 참조 |
| errors | array[string] | required | 에러/제한 | `DOCS_DIR_NOT_FOUND` 등 |

- **결정론/트렁케이션 규칙**
  - 문서 스니펫은 `max_snippet_chars`로 절단되며, 절단 시 `SNIPPET_TRUNCATED` 오류가 기록된다.
  - `errors`는 `sorted(set(...))`로 중복 제거 및 정렬.

- **미구현 엔드포인트**: 없음.

---

## Code / Module Specification

### Modules (app/)
- **`app/main.py`**
  - **책임**: FastAPI 앱 생성 및 라우터 결합.
  - **주요 함수**: `health()` (`GET /health`) — 항상 `{ "status": "ok" }` 반환.
  - **호출 관계**: `app.api.mcp.router`를 `/mcp` prefix로 포함.
  - **불변식**: 헬스 응답은 결정론적이며 민감 정보 미포함.

- **`app/api/mcp.py`**
  - **책임**: MCP API 라우트 정의 및 Pydantic 요청/응답 모델 제공.
  - **주요 엔드포인트 핸들러**: `analyze`, `standardize_spec`, `standardize_spec_with_evidence`, `callers`, `external_deps`, `common_reusability`, `common_rules_template`, `common_call_graph`, `migration_mapping_strategy`, `migration_mybatis_difficulty`, `migration_transaction_boundary`, `quality_performance_risk`, `quality_db_dependency`.
  - **불변식**: 응답 구조는 Pydantic 모델에 의해 고정되며, SQL 원문은 응답에 포함되지 않는다.

- **`app/services/*`** (서비스 모듈)
  - 각 모듈은 분석/추천 로직을 담당하며, 입력 SQL을 요약/해시로만 로깅한다.
  - 정렬/중복 제거/캡 제한을 통해 결정론을 보장한다.

- **`app/tests/test_health.py`**
  - `/health` 응답이 `{ "status": "ok" }`인지 검증하는 스모크 테스트.

### Modules (tests/)
- **공통 구성**: `tests/conftest.py`에서 FastAPI TestClient 및 공통 fixture 설정.
- **엔드포인트별 스모크/회귀 테스트**
  - `tests/test_health.py`: `/health` 응답 확인.
  - `tests/test_no_sql_echo.py`: SQL 원문이 응답에 노출되지 않는지 회귀 검사.
  - `tests/test_determinism_smoke.py`: 결정론(정렬/중복 제거/캡 제한) 스모크 확인.
  - `tests/test_mcp_analyze_*`: analyze 하위 기능(참조/트랜잭션/임팩트/제어흐름/데이터변경/에러처리).
  - `tests/test_mcp_common_*`: callers/external-deps/reusability/rules-template/call-graph.
  - `tests/test_mcp_migration_*`: mapping-strategy/mybatis-difficulty/transaction-boundary.
  - `tests/test_mcp_quality_*`: performance-risk/db-dependency.
  - `tests/test_mcp_standardize_spec*.py`: 표준화 스펙 및 evidence 경로.

---

## Services (분석/추천 모듈 상세)

### `app/services/tsql_analyzer.py`
- **주요 함수**: `analyze_references`, `analyze_transactions`, `analyze_migration_impacts`, `analyze_control_flow`, `analyze_data_changes`, `analyze_error_handling`.
- **입력/출력 요약**
  - 입력: `sql: str`, `dialect: str = "tsql"`.
  - 출력: `dict` 기반 결과(각 엔드포인트의 Pydantic 모델에 매핑).
- **에러 처리**: 파서 실패 시 `errors`에 `parse_error` 기록 후 fallback 정규식 분석.
- **결정론/캡 규칙**
  - 참조/신호/리스트는 정렬/중복 제거.
  - 제어 흐름 그래프는 노드/엣지 제한(`CONTROL_FLOW_NODE_LIMIT`, `CONTROL_FLOW_EDGE_LIMIT`) 적용.
  - 에러 처리 신호/리턴 값 등은 상한(예: 10~15개) 제한.

### `app/services/tsql_callers.py`
- **주요 함수**: `find_callers`.
- **입력**: `target`, `target_type`, `objects: list[SqlObject]`, `options: CallerOptions`.
- **출력**: `callers` 목록 및 요약.
- **에러 처리/제한**
  - 객체 수 제한 500개, SQL 총 길이 제한 1,000,000자.
  - 제한 초과 시 `errors`에 상세 메시지 기록.
- **결정론**: 호출 횟수 내림차순 + 이름 정렬, signals 상한 10개.

### `app/services/tsql_call_graph.py`
- **주요 함수**: `build_call_graph`.
- **입력**: `objects: list[SqlObject]`, `options: Options`.
- **출력**: 그래프 노드/엣지 + 위상 정보.
- **제한 규칙**: `max_nodes`, `max_edges` 초과 시 `summary.truncated` 및 `errors`에 기록.

### `app/services/tsql_external_deps.py`
- **주요 함수**: `analyze_external_dependencies`.
- **입력**: `sql`, `options`(case_insensitive, max_items, name/type 등).
- **출력**: 링크드 서버/크로스DB/원격 실행 등 의존성 상세.
- **제한 규칙**: 항목 수 `max_items` 초과 시 `errors`에 `max_items_exceeded` 기록.

### `app/services/tsql_business_rules.py`
- **주요 함수**: `analyze_business_rules`.
- **입력**: `sql`, `dialect`, `case_insensitive`, `max_rules`, `max_templates`.
- **출력**: 규칙 목록, 템플릿 제안, 요약(트렁케이션 여부 포함).
- **제한 규칙**: 규칙/템플릿 수 제한 발생 시 `summary.truncated=true`, `errors`에 기록.

### `app/services/tsql_reusability.py`
- **주요 함수**: `evaluate_reusability`.
- **입력**: `sql`, `dialect`, `max_reason_items`.
- **출력**: 재사용성 점수/등급/사유/권장사항.
- **제한 규칙**: 사유/권장사항 상한 적용, 정렬/중복 제거.

### `app/services/tsql_mapping_strategy.py`
- **주요 함수**: `recommend_mapping_strategy`.
- **입력**: `sql`, `obj_type`, `dialect`, `case_insensitive`, `target_style`, `max_items`.
- **출력**: 매핑 전략/패턴/사유/권장사항.
- **결정론 규칙**
  - 위험 신호 및 난이도 계산은 고정된 규칙 기반.
  - `max_items` 초과 시 사유/권장사항이 절단되고 `errors`에 기록.

### `app/services/tsql_mybatis_difficulty.py`
- **주요 함수**: `evaluate_mybatis_difficulty`.
- **입력**: `sql`, `obj_type`, `dialect`, `case_insensitive`, `max_reason_items`.
- **출력**: 난이도 점수/요인/권장사항.
- **제한 규칙**: `max_reason_items` 초과 시 `summary.truncated=true` 및 `errors`에 기록.

### `app/services/tsql_tx_boundary.py`
- **주요 함수**: `recommend_transaction_boundary`.
- **입력**: `sql`, `obj_type`, `dialect`, `case_insensitive`, `prefer_service_layer_tx`, `max_items`.
- **출력**: 트랜잭션 경계 요약/제안/안티패턴/Java 스니펫.
- **제한 규칙**: `max_items` 초과 시 제안 목록이 절단되고 `errors`에 기록.

### `app/services/tsql_performance_risk.py`
- **주요 함수**: `analyze_performance_risk`.
- **입력**: `sql`, `dialect`, `case_insensitive`, `max_findings`.
- **출력**: 리스크 점수/탐지 항목/권장사항.
- **제한 규칙**: `max_findings` 초과 시 `summary.truncated=true` 및 `errors`에 기록.

### `app/services/tsql_db_dependency.py`
- **주요 함수**: `analyze_db_dependency`.
- **입력**: `sql`, `dialect`, `case_insensitive`, `schema_sensitive`, `max_items`.
- **출력**: 의존도 요약/지표/의존성 항목.
- **제한 규칙**: `max_items` 초과 시 `summary.truncated=true` 및 `errors`에 기록.

### `app/services/tsql_standardization_spec.py`
- **주요 함수**: `build_standardization_spec`.
- **입력**: `name`, `obj_type`, `sql` 또는 `inputs`, `options`.
- **출력**: 표준화 스펙 통합 결과.
- **결정론/제한 규칙**
  - 섹션별 정렬/중복 제거.
  - `max_items_per_section` 초과 시 해당 섹션에서 절단 + `errors`에 기록.

### `app/services/rag_lexical.py`
- **주요 함수**: `load_documents`, `build_index`, `search`, `extract_query_terms`, `build_snippet`, `build_pattern_recommendations`.
- **목적**: 표준 문서(텍스트/마크다운)를 로드해 렉시컬 인덱스를 구성하고 검색 결과를 제공.
- **제한 규칙**: 스니펫 길이는 `max_snippet_chars`로 절단.

---

## Utilities

### `app/services/safe_sql.py`
- **`summarize_sql(sql)`**: SQL 길이와 SHA-256 해시의 앞 8자리(`sha256_8`)만 계산하여 로그에 사용.
- **`strip_comments_and_strings(sql)`**: 주석/문자열 리터럴을 제거해 분석용 정규식 탐지 품질을 높임.
- **불변식**: 원문 SQL을 로그/응답에 노출하지 않도록 모든 서비스가 이 유틸을 사용.

---

## Data Models (Pydantic)

> 모든 모델은 `app/api/mcp.py`에 정의되어 있으며, 아래 표는 필드/타입/기본값/제약을 요약한다.

### Analyze

#### `AnalyzeRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| sql | string | required | - | 분석 대상 SQL | `min_length=1` |
| dialect | string | optional | "tsql" | SQL 파서 dialect |  |

#### `References`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| tables | array[string] | required | - | 테이블 참조 | 정렬/중복 제거 |
| functions | array[string] | required | - | 함수 참조 | 정렬/중복 제거 |

#### `TransactionSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| uses_transaction | bool | required | - | 트랜잭션 사용 여부 |  |
| begin_count | int | required | - | BEGIN TRAN 수 |  |
| commit_count | int | required | - | COMMIT 수 |  |
| rollback_count | int | required | - | ROLLBACK 수 |  |
| savepoint_count | int | required | - | SAVE TRAN 수 |  |
| has_try_catch | bool | required | - | TRY/CATCH 여부 |  |
| xact_abort | string \| null | required | - | SET XACT_ABORT 값 | `ON/OFF/None` |
| isolation_level | string \| null | required | - | Isolation level |  |
| signals | array[string] | required | - | 신호 목록 | 정렬/중복 제거 |

#### `ImpactItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 영향 ID |  |
| category | string | required | - | 카테고리 |  |
| severity | string | required | - | 심각도 |  |
| title | string | required | - | 제목 |  |
| signals | array[string] | required | - | 신호 |  |
| details | string | required | - | 상세 설명 |  |

#### `MigrationImpacts`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_impact | bool | required | - | 영향 존재 여부 |  |
| items | array[ImpactItem] | required | - | 영향 항목 | 심각도 정렬 |

#### `ControlFlowSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_branching | bool | required | - | 분기 여부 |  |
| has_loops | bool | required | - | 루프 여부 |  |
| has_try_catch | bool | required | - | TRY/CATCH 여부 |  |
| has_goto | bool | required | - | GOTO 여부 |  |
| has_return | bool | required | - | RETURN 여부 |  |
| branch_count | int | required | - | 분기 개수 |  |
| loop_count | int | required | - | 루프 개수 |  |
| return_count | int | required | - | RETURN 개수 |  |
| goto_count | int | required | - | GOTO 개수 |  |
| max_nesting_depth | int | required | - | 최대 중첩 깊이 |  |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |

#### `ControlFlowNode`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 노드 ID |  |
| type | string | required | - | 노드 타입 |  |
| label | string | required | - | 라벨 |  |

#### `ControlFlowEdge`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| from | string | required | - | 출발 노드 ID | 필드명은 `alias="from"` |
| to | string | required | - | 도착 노드 ID |  |
| label | string | required | - | 라벨 |  |

#### `ControlFlowGraph`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| nodes | array[ControlFlowNode] | required | - | 노드 목록 | 캡 제한 가능 |
| edges | array[ControlFlowEdge] | required | - | 엣지 목록 | 캡 제한 가능 |

#### `ControlFlow`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| summary | ControlFlowSummary | required | - | 요약 |  |
| graph | ControlFlowGraph | required | - | 그래프 |  |
| signals | array[string] | required | - | 신호 | 제한 적용 |

#### `DataChangeOperation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| count | int | required | - | 작업 개수 |  |
| tables | array[string] | required | - | 테이블 목록 | 정렬/중복 제거 |

#### `DataChangeOperations`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| insert | DataChangeOperation | required | - | INSERT 요약 |  |
| update | DataChangeOperation | required | - | UPDATE 요약 |  |
| delete | DataChangeOperation | required | - | DELETE 요약 |  |
| merge | DataChangeOperation | required | - | MERGE 요약 |  |
| truncate | DataChangeOperation | required | - | TRUNCATE 요약 |  |
| select_into | DataChangeOperation | required | - | SELECT INTO 요약 |  |

#### `TableOperation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| table | string | required | - | 테이블명 |  |
| ops | array[string] | required | - | 수행 작업 | 정렬/중복 제거 |

#### `DataChanges`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_writes | bool | required | - | 쓰기 여부 |  |
| operations | DataChangeOperations | required | - | 작업 요약 |  |
| table_operations | array[TableOperation] | required | - | 테이블별 작업 | 테이블명 정렬 |
| signals | array[string] | required | - | 신호 | 정렬/중복 제거 |
| notes | array[string] | required | - | 보충 설명 | 대상 테이블 미확정 시 기록 |

#### `ErrorHandling`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_try_catch | bool | required | - | TRY/CATCH 여부 |  |
| try_count | int | required | - | TRY 수 |  |
| catch_count | int | required | - | CATCH 수 |  |
| uses_throw | bool | required | - | THROW 사용 여부 |  |
| throw_count | int | required | - | THROW 수 |  |
| uses_raiserror | bool | required | - | RAISERROR 사용 여부 |  |
| raiserror_count | int | required | - | RAISERROR 수 |  |
| uses_at_at_error | bool | required | - | @@ERROR 사용 여부 |  |
| at_at_error_count | int | required | - | @@ERROR 수 |  |
| uses_error_functions | array[string] | required | - | ERROR_* 함수 목록 | 최대 10개 |
| uses_print | bool | required | - | PRINT 사용 여부 |  |
| print_count | int | required | - | PRINT 수 |  |
| uses_return | bool | required | - | RETURN 사용 여부 |  |
| return_count | int | required | - | RETURN 수 |  |
| return_values | array[int] | required | - | RETURN 값 목록 | 최대 10개 |
| uses_output_error_params | bool | required | - | OUTPUT 에러 파라미터 여부 |  |
| output_error_params | array[string] | required | - | OUTPUT 에러 파라미터 목록 | 최대 10개 |
| signals | array[string] | required | - | 신호 | 최대 15개 |
| notes | array[string] | required | - | 보충 설명 |  |

#### `AnalyzeResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| references | References | required | - | 참조 목록 |  |
| transactions | TransactionSummary | required | - | 트랜잭션 요약 |  |
| migration_impacts | MigrationImpacts | required | - | 마이그레이션 영향 |  |
| control_flow | ControlFlow | required | - | 제어 흐름 |  |
| data_changes | DataChanges | required | - | 데이터 변경 |  |
| error_handling | ErrorHandling | required | - | 오류 처리 |  |
| errors | array[string] | required | - | 오류 |  |

### Standardize Spec

#### `StandardizeSpecObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `StandardizeSpecOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| include_sections | array[string] \| null | optional | null | 포함 섹션 | 미지정 시 전체 |
| max_items_per_section | int | optional | 50 | 섹션별 최대 항목 |  |

#### `StandardizeSpecRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| object | StandardizeSpecObject | required | - | 대상 객체 |  |
| sql | string \| null | optional | null | 분석 SQL | `sql` 또는 `inputs`만 허용 |
| inputs | object \| null | optional | null | 사전 입력 | `sql` 없을 때 필요 |
| options | StandardizeSpecOptions | optional | defaults | 옵션 |  |

#### `StandardizeSpecObjectResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| normalized | string | required | - | 정규화 이름 | 소문자 + 대괄호 제거 |

#### `StandardizeSpecSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| one_liner | string | required | - | 한 줄 요약 |  |
| risk_level | string | required | - | 리스크 수준 |  |
| difficulty_level | string | required | - | 난이도 수준 |  |

#### `StandardizeSpecTemplate`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 템플릿 ID |  |
| source | string | required | - | 소스 |  |
| confidence | float | required | - | 신뢰도 |  |

#### `StandardizeSpecRule`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 규칙 ID |  |
| kind | string | required | - | 규칙 유형 |  |
| condition | string | required | - | 조건 |  |
| action | string | required | - | 수행 동작 |  |

#### `StandardizeSpecDependencies`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| tables | array[string] | required | - | 테이블 | 정렬/중복 제거 |
| functions | array[string] | required | - | 함수 | 정렬/중복 제거 |
| cross_db | array[string] | required | - | 크로스DB | 정렬/중복 제거 |
| linked_servers | array[string] | required | - | 링크드 서버 | 정렬/중복 제거 |

#### `StandardizeSpecTransactions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| recommended_boundary | string \| null | required | - | 권장 경계 |  |
| propagation | string \| null | required | - | 전파 속성 |  |
| isolation_level | string \| null | required | - | 격리 수준 |  |

#### `StandardizeSpecMyBatis`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| approach | string | required | - | 접근 방식 |  |
| difficulty_score | int \| null | required | - | 난이도 점수 |  |

#### `StandardizeSpecRisks`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| migration_impacts | array[string] | required | - | 마이그레이션 리스크 |  |
| performance | array[string] | required | - | 성능 리스크 |  |
| db_dependency | array[string] | required | - | DB 의존도 리스크 |  |

#### `StandardizeSpecRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장사항 ID |  |
| message | string | required | - | 메시지 |  |

#### `StandardizeSpecEvidence`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| signals | object | required | - | 증거 신호 |  |

#### `StandardizeSpecPayload`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| tags | array[string] | required | - | 태그 | 정렬/중복 제거 |
| summary | StandardizeSpecSummary | required | - | 요약 |  |
| templates | array[StandardizeSpecTemplate] | required | - | 템플릿 | 섹션 캡 적용 |
| rules | array[StandardizeSpecRule] | required | - | 규칙 | 섹션 캡 적용 |
| dependencies | StandardizeSpecDependencies | required | - | 의존성 |  |
| transactions | StandardizeSpecTransactions | required | - | 트랜잭션 |  |
| mybatis | StandardizeSpecMyBatis | required | - | MyBatis |  |
| risks | StandardizeSpecRisks | required | - | 리스크 |  |
| recommendations | array[StandardizeSpecRecommendation] | required | - | 권장사항 | 섹션 캡 적용 |
| evidence | StandardizeSpecEvidence | required | - | 증거 |  |

#### `StandardizeSpecResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | StandardizeSpecObjectResponse | required | - | 대상 정보 |  |
| spec | StandardizeSpecPayload | required | - | 스펙 본문 |  |
| errors | array[string] | required | - | 에러 |  |

#### `StandardizeSpecWithEvidenceOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| docs_dir | string | optional | "data/standard_docs" | 문서 디렉터리 |  |
| top_k | int | optional | 5 | 상위 검색 개수 |  |
| max_snippet_chars | int | optional | 280 | 스니펫 길이 |  |

#### `StandardizeSpecWithEvidenceRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| object | StandardizeSpecObject | required | - | 대상 객체 |  |
| sql | string | required | - | 분석 SQL |  |
| options | StandardizeSpecWithEvidenceOptions | optional | defaults | 증거 옵션 |  |

#### `StandardizeSpecEvidenceDocument`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| doc_id | string | required | - | 문서 ID |  |
| title | string | required | - | 제목 |  |
| source | string | required | - | 소스 |  |
| score | float | required | - | 스코어 | 소수점 6자리 반올림 |
| snippet | string | required | - | 스니펫 | `max_snippet_chars` 절단 가능 |

#### `StandardizeSpecPatternRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 권장 메시지 |  |
| source_doc_id | string \| null | required | - | 문서 ID |  |

#### `StandardizeSpecWithEvidencePayload`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| query_terms | array[string] | required | - | 검색어 | 정렬/중복 제거, 최대 30개 |
| documents | array[StandardizeSpecEvidenceDocument] | required | - | 근거 문서 |  |
| pattern_recommendations | array[StandardizeSpecPatternRecommendation] | required | - | 패턴 권장 |  |

#### `StandardizeSpecWithEvidenceResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | StandardizeSpecObjectResponse | required | - | 대상 정보 |  |
| spec | StandardizeSpecPayload | required | - | 스펙 본문 |  |
| evidence | StandardizeSpecWithEvidencePayload | required | - | 근거 문서 |  |
| errors | array[string] | required | - | 에러 | 중복 제거 후 정렬 |

### Callers

#### `CallersOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| schema_sensitive | bool | optional | false | 스키마 민감도 |  |
| include_self | bool | optional | false | 자기 자신 포함 여부 |  |

#### `CallersObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |

#### `CallersRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| target | string | required | - | 대상 이름 |  |
| target_type | string \| null | optional | null | 대상 유형 |  |
| objects | array[CallersObject] | required | - | 객체 목록 | 최대 500개 처리 |
| options | CallersOptions | optional | defaults | 옵션 |  |

#### `CallersTarget`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 대상 이름 |  |
| type | string | required | - | 대상 유형 |  |
| normalized | string | required | - | 정규화 이름 | 소문자/대괄호 제거 |

#### `CallersSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_callers | bool | required | - | 호출자 존재 여부 |  |
| caller_count | int | required | - | 호출자 수 |  |
| total_calls | int | required | - | 총 호출 수 |  |

#### `CallerResult`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 호출자 이름 |  |
| type | string | required | - | 호출자 유형 |  |
| call_count | int | required | - | 호출 횟수 |  |
| call_kinds | array[string] | required | - | 호출 유형 | 정렬/중복 제거 |
| signals | array[string] | required | - | 신호 | 최대 10개 |

#### `CallersResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| target | CallersTarget | required | - | 대상 정보 |  |
| summary | CallersSummary | required | - | 요약 |  |
| callers | array[CallerResult] | required | - | 호출자 목록 | 정렬 규칙 적용 |
| errors | array[string] | required | - | 에러 | 제한/절단 포함 |

### External Dependencies

#### `ExternalDepsOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| max_items | int | optional | 200 | 최대 항목 | `ge=1` |

#### `ExternalDepsRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | ExternalDepsOptions | optional | defaults | 옵션 |  |

#### `ExternalDepsObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `ExternalDepsSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_external_deps | bool | required | - | 외부 의존성 여부 |  |
| linked_server_count | int | required | - | 링크드 서버 개수 |  |
| cross_db_count | int | required | - | 크로스 DB 개수 |  |
| remote_exec_count | int | required | - | 원격 실행 개수 |  |
| openquery_count | int | required | - | OPENQUERY 개수 |  |
| opendatasource_count | int | required | - | OPENDATASOURCE 개수 |  |

#### `LinkedServerItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 서버명 |  |
| signals | array[string] | required | - | 신호 |  |

#### `CrossDatabaseItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| database | string | required | - | DB 명 |  |
| schema | string | required | - | 스키마 | 필드명은 `alias="schema"` |
| object | string | required | - | 오브젝트 |  |
| kind | string | required | - | 종류 |  |

#### `TargetDependencyItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| target | string | required | - | 대상 |  |
| kind | string | required | - | 종류 |  |
| signals | array[string] | required | - | 신호 |  |

#### `OtherDependencyItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | ID |  |
| kind | string | required | - | 종류 |  |
| signals | array[string] | required | - | 신호 |  |

#### `ExternalDependencies`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| linked_servers | array[LinkedServerItem] | required | - | 링크드 서버 | 정렬/캡 적용 |
| cross_database | array[CrossDatabaseItem] | required | - | 크로스 DB | 정렬/캡 적용 |
| remote_exec | array[TargetDependencyItem] | required | - | 원격 실행 | 정렬/캡 적용 |
| openquery | array[TargetDependencyItem] | required | - | OPENQUERY | 정렬/캡 적용 |
| opendatasource | array[TargetDependencyItem] | required | - | OPENDATASOURCE | 정렬/캡 적용 |
| others | array[OtherDependencyItem] | required | - | 기타 | 정렬/캡 적용 |

#### `ExternalDepsResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | ExternalDepsObject | required | - | 대상 정보 |  |
| summary | ExternalDepsSummary | required | - | 요약 |  |
| external_dependencies | ExternalDependencies | required | - | 의존성 상세 |  |
| signals | array[string] | required | - | 신호 | 정렬/중복 제거, 최대 15개 |
| errors | array[string] | required | - | 에러 |  |

### Reusability

#### `ReusabilityOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| max_reason_items | int | optional | 20 | 최대 사유 항목 | `ge=1` |

#### `ReusabilityRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | ReusabilityOptions | optional | defaults | 옵션 |  |

#### `ReusabilityObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `ReusabilitySummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| score | int | required | - | 점수 |  |
| grade | string | required | - | 등급 |  |
| is_candidate | bool | required | - | 후보 여부 |  |
| candidate_type | string \| null | required | - | 후보 유형 |  |

#### `ReusabilitySignals`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| read_only | bool | required | - | 읽기 전용 여부 |  |
| has_writes | bool | required | - | 쓰기 여부 |  |
| uses_transaction | bool | required | - | 트랜잭션 사용 |  |
| has_dynamic_sql | bool | required | - | 동적 SQL |  |
| has_cursor | bool | required | - | 커서 사용 |  |
| uses_temp_objects | bool | required | - | 임시 객체 |  |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |
| table_count | int | required | - | 테이블 수 |  |
| function_call_count | int | required | - | 함수 호출 수 |  |
| has_try_catch | bool | required | - | TRY/CATCH |  |
| error_signaling | array[string] | required | - | 오류 신호 | 정렬/중복 제거 |

#### `ReusabilityReason`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 사유 ID |  |
| impact | string | required | - | 영향 |  |
| weight | int | required | - | 가중치 |  |
| message | string | required | - | 메시지 |  |

#### `ReusabilityRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 메시지 |  |

#### `ReusabilityResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | ReusabilityObject | required | - | 대상 정보 |  |
| summary | ReusabilitySummary | required | - | 요약 |  |
| signals | ReusabilitySignals | required | - | 신호 |  |
| reasons | array[ReusabilityReason] | required | - | 사유 | 정렬/캡 적용 |
| recommendations | array[ReusabilityRecommendation] | required | - | 권장사항 | 정렬/캡 적용 |
| errors | array[string] | required | - | 에러 |  |

### Business Rules

#### `BusinessRulesOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| max_rules | int | optional | 100 | 최대 규칙 | `ge=1` |
| max_templates | int | optional | 150 | 최대 템플릿 | `ge=1` |

#### `BusinessRulesRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | BusinessRulesOptions | optional | defaults | 옵션 |  |

#### `BusinessRulesObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `BusinessRulesSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_rules | bool | required | - | 규칙 존재 여부 |  |
| rule_count | int | required | - | 규칙 수 |  |
| template_suggestion_count | int | required | - | 템플릿 제안 수 |  |
| truncated | bool | required | - | 제한 적용 여부 |  |

#### `BusinessRule`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 규칙 ID |  |
| kind | string | required | - | 규칙 유형 |  |
| confidence | float | required | - | 신뢰도 |  |
| condition | string | required | - | 조건 |  |
| action | string | required | - | 동작 |  |
| signals | array[string] | required | - | 신호 | 정렬/중복 제거 |

#### `BusinessRuleTemplateSuggestion`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| rule_id | string | required | - | 규칙 ID |  |
| template_id | string | required | - | 템플릿 ID |  |
| confidence | float | required | - | 신뢰도 |  |
| rationale | string | required | - | 근거 |  |

#### `BusinessRulesResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | BusinessRulesObject | required | - | 대상 정보 |  |
| summary | BusinessRulesSummary | required | - | 요약 |  |
| rules | array[BusinessRule] | required | - | 규칙 목록 | 정렬/캡 적용 |
| template_suggestions | array[BusinessRuleTemplateSuggestion] | required | - | 템플릿 제안 | 정렬/캡 적용 |
| signals | array[string] | required | - | 신호 |  |
| errors | array[string] | required | - | 에러 |  |

### Call Graph

#### `CallGraphOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| schema_sensitive | bool | optional | false | 스키마 민감도 |  |
| include_functions | bool | optional | true | 함수 포함 |  |
| include_procedures | bool | optional | true | 프로시저 포함 |  |
| ignore_dynamic_exec | bool | optional | true | 동적 실행 무시 |  |
| max_nodes | int | optional | 500 | 최대 노드 | `ge=1` |
| max_edges | int | optional | 2000 | 최대 엣지 | `ge=1` |

#### `CallGraphObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |

#### `CallGraphRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| objects | array[CallGraphObject] | required | - | 객체 목록 |  |
| options | CallGraphOptions | optional | defaults | 옵션 |  |

#### `CallGraphSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| object_count | int | required | - | 입력 객체 수 |  |
| node_count | int | required | - | 노드 수 |  |
| edge_count | int | required | - | 엣지 수 |  |
| has_cycles | bool | required | - | 순환 여부 |  |
| truncated | bool | required | - | 제한 적용 여부 |  |

#### `CallGraphNode`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 노드 ID |  |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `CallGraphEdge`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| from | string | required | - | 출발 노드 ID | 필드명은 `alias="from"` |
| to | string | required | - | 도착 노드 ID |  |
| kind | string | required | - | 호출 종류 |  |
| count | int | required | - | 호출 수 |  |
| signals | array[string] | required | - | 신호 | 정렬/중복 제거 |

#### `CallGraph`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| nodes | array[CallGraphNode] | required | - | 노드 목록 |  |
| edges | array[CallGraphEdge] | required | - | 엣지 목록 |  |

#### `CallGraphTopology`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| roots | array[string] | required | - | 루트 노드 | 정렬/중복 제거 |
| leaves | array[string] | required | - | 리프 노드 | 정렬/중복 제거 |
| in_degree | object | required | - | 진입 차수 | 노드 ID -> count |
| out_degree | object | required | - | 진출 차수 | 노드 ID -> count |

#### `CallGraphError`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 에러 ID |  |
| message | string | required | - | 메시지 |  |
| object | string \| null | optional | null | 관련 객체 |  |

#### `CallGraphResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| summary | CallGraphSummary | required | - | 요약 |  |
| graph | CallGraph | required | - | 그래프 |  |
| topology | CallGraphTopology | required | - | 위상 |  |
| errors | array[CallGraphError] | required | - | 에러 |  |

### Mapping Strategy

#### `MappingStrategyOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| target_style | "rewrite" \| "call_sp_first" | optional | "rewrite" | 목표 스타일 |  |
| max_items | int | optional | 30 | 최대 항목 | `ge=1` |

#### `MappingStrategyRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | MappingStrategyOptions | optional | defaults | 옵션 |  |

#### `MappingStrategyObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `MappingStrategySummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| approach | string | required | - | 접근 방식 |  |
| confidence | float | required | - | 신뢰도 |  |
| difficulty | string | required | - | 난이도 |  |
| is_recommended | bool | required | - | 추천 여부 |  |

#### `MappingStrategySignals`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| read_only | bool | required | - | 읽기 전용 |  |
| has_writes | bool | required | - | 쓰기 여부 |  |
| writes_kind | array[string] | required | - | 쓰기 유형 | 정렬/중복 제거 |
| uses_transaction | bool | required | - | 트랜잭션 사용 |  |
| has_dynamic_sql | bool | required | - | 동적 SQL |  |
| has_cursor | bool | required | - | 커서 |  |
| uses_temp_objects | bool | required | - | 임시 객체 |  |
| has_merge | bool | required | - | MERGE 사용 |  |
| has_identity_retrieval | bool | required | - | IDENTITY 획득 |  |
| has_output_clause | bool | required | - | OUTPUT 사용 |  |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |
| table_count | int | required | - | 테이블 수 |  |
| has_try_catch | bool | required | - | TRY/CATCH |  |
| error_signaling | array[string] | required | - | 오류 신호 | 정렬/중복 제거 |

#### `StrategyPattern`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 패턴 ID |  |
| message | string | required | - | 메시지 |  |

#### `MappingStrategyPlan`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| migration_path | array[string] | required | - | 마이그레이션 경로 | 정렬/중복 제거 |
| recommended_patterns | array[StrategyPattern] | required | - | 권장 패턴 | 정렬/캡 적용 |
| anti_patterns | array[StrategyPattern] | required | - | 안티 패턴 | 정렬/캡 적용 |

#### `MapperMethod`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 메서드명 |  |
| kind | string | required | - | 유형 |  |
| parameter_style | string | required | - | 파라미터 스타일 |  |
| return_style | string | required | - | 반환 스타일 |  |

#### `XmlTemplate`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| statement_tag | string | required | - | 태그 |  |
| skeleton | string | required | - | 스켈레톤 |  |
| dynamic_tags | array[string] | required | - | 다이내믹 태그 | 정렬/중복 제거 |

#### `MyBatisMapping`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| mapper_method | MapperMethod | required | - | 매퍼 메서드 |  |
| xml_template | XmlTemplate | required | - | XML 템플릿 |  |

#### `ServicePattern`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| transactional | bool | required | - | 트랜잭션 여부 |  |
| exception_mapping | string | required | - | 예외 매핑 |  |

#### `DtoSuggestion`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | DTO ID |  |
| fields | array[string] | required | - | 필드 | 정렬/중복 제거 |
| notes | string | required | - | 설명 |  |

#### `JavaMapping`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| service_pattern | ServicePattern | required | - | 서비스 패턴 |  |
| dto_suggestions | array[DtoSuggestion] | required | - | DTO 제안 | 정렬/중복 제거 |

#### `MappingStrategyReason`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 사유 ID |  |
| weight | int | required | - | 가중치 |  |
| message | string | required | - | 메시지 |  |

#### `MappingStrategyRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 메시지 |  |

#### `MappingStrategyResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | MappingStrategyObject | required | - | 대상 정보 |  |
| summary | MappingStrategySummary | required | - | 요약 |  |
| signals | MappingStrategySignals | required | - | 신호 |  |
| strategy | MappingStrategyPlan | required | - | 전략 |  |
| mybatis | MyBatisMapping | required | - | MyBatis |  |
| java | JavaMapping | required | - | Java |  |
| reasons | array[MappingStrategyReason] | required | - | 사유 |  |
| recommendations | array[MappingStrategyRecommendation] | required | - | 권장사항 |  |
| errors | array[string] | required | - | 에러 |  |

### Transaction Boundary

#### `TxBoundaryOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| prefer_service_layer_tx | bool | optional | true | 서비스 레이어 선호 |  |
| max_items | int | optional | 30 | 최대 항목 | `ge=1` |

#### `TxBoundaryRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | TxBoundaryOptions | optional | defaults | 옵션 |  |

#### `TxBoundaryObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `TxBoundarySummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| recommended_boundary | string | required | - | 권장 경계 |  |
| transactional | bool | required | - | 트랜잭션 여부 |  |
| propagation | string | required | - | 전파 속성 |  |
| isolation_level | string \| null | required | - | 격리 수준 |  |
| read_only | bool | required | - | 읽기 전용 |  |
| confidence | float | required | - | 신뢰도 |  |

#### `TxBoundarySignals`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| has_writes | bool | required | - | 쓰기 여부 |  |
| write_ops | array[string] | required | - | 쓰기 유형 | 정렬/중복 제거 |
| uses_transaction_in_sql | bool | required | - | SQL 내 트랜잭션 |  |
| begin_count | int | required | - | BEGIN 수 |  |
| commit_count | int | required | - | COMMIT 수 |  |
| rollback_count | int | required | - | ROLLBACK 수 |  |
| has_try_catch | bool | required | - | TRY/CATCH |  |
| xact_abort | string \| null | required | - | XACT_ABORT |  |
| isolation_level_in_sql | string \| null | required | - | 격리 수준 |  |
| has_dynamic_sql | bool | required | - | 동적 SQL |  |
| has_cursor | bool | required | - | 커서 |  |
| uses_temp_objects | bool | required | - | 임시 객체 |  |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |
| error_signaling | array[string] | required | - | 오류 신호 | 정렬/중복 제거 |

#### `TxBoundaryItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | ID |  |
| message | string | required | - | 메시지 |  |

#### `TxBoundarySnippets`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| annotation_example | string | required | - | 어노테이션 예시 |  |
| notes | array[string] | required | - | 주석 | 정렬/중복 제거 |

#### `TxBoundaryResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | TxBoundaryObject | required | - | 대상 정보 |  |
| summary | TxBoundarySummary | required | - | 요약 |  |
| signals | TxBoundarySignals | required | - | 신호 |  |
| suggestions | array[TxBoundaryItem] | required | - | 권장 항목 |  |
| anti_patterns | array[TxBoundaryItem] | required | - | 안티 패턴 |  |
| java_snippets | TxBoundarySnippets | required | - | Java 스니펫 |  |
| errors | array[string] | required | - | 에러 |  |

### MyBatis Difficulty

#### `MyBatisDifficultyOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| max_reason_items | int | optional | 25 | 최대 항목 |  |

#### `MyBatisDifficultyRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | MyBatisDifficultyOptions | optional | defaults | 옵션 |  |

#### `MyBatisDifficultyObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `MyBatisDifficultySummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| difficulty_score | int | required | - | 난이도 점수 |  |
| difficulty_level | string | required | - | 난이도 레벨 |  |
| estimated_work_units | int | required | - | 작업량 추정 |  |
| is_rewrite_recommended | bool | required | - | 재작성 추천 |  |
| confidence | float | required | - | 신뢰도 |  |
| truncated | bool | required | - | 제한 적용 여부 |  |

#### `MyBatisDifficultySignals`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| table_count | int | required | - | 테이블 수 |  |
| function_call_count | int | required | - | 함수 호출 수 |  |
| has_writes | bool | required | - | 쓰기 여부 |  |
| write_ops | array[string] | required | - | 쓰기 유형 | 정렬/중복 제거 |
| uses_transaction | bool | required | - | 트랜잭션 사용 |  |
| has_dynamic_sql | bool | required | - | 동적 SQL |  |
| has_cursor | bool | required | - | 커서 |  |
| uses_temp_objects | bool | required | - | 임시 객체 |  |
| has_merge | bool | required | - | MERGE |  |
| has_output_clause | bool | required | - | OUTPUT |  |
| has_identity_retrieval | bool | required | - | IDENTITY |  |
| has_try_catch | bool | required | - | TRY/CATCH |  |
| error_signaling | array[string] | required | - | 오류 신호 | 정렬/중복 제거 |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |

#### `MyBatisDifficultyFactor`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 요인 ID |  |
| points | int | required | - | 점수 |  |
| message | string | required | - | 메시지 |  |

#### `MyBatisDifficultyRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 메시지 |  |

#### `MyBatisDifficultyResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | MyBatisDifficultyObject | required | - | 대상 정보 |  |
| summary | MyBatisDifficultySummary | required | - | 요약 |  |
| signals | MyBatisDifficultySignals | required | - | 신호 |  |
| factors | array[MyBatisDifficultyFactor] | required | - | 요인 | 정렬/캡 적용 |
| recommendations | array[MyBatisDifficultyRecommendation] | required | - | 권장사항 | 정렬/캡 적용 |
| errors | array[string] | required | - | 에러 |  |

### Performance Risk

#### `PerformanceRiskOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| max_findings | int | optional | 50 | 최대 탐지 |  |

#### `PerformanceRiskRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | PerformanceRiskOptions | optional | defaults | 옵션 |  |

#### `PerformanceRiskObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `PerformanceRiskSummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| risk_score | int | required | - | 리스크 점수 |  |
| risk_level | string | required | - | 리스크 레벨 |  |
| finding_count | int | required | - | 탐지 수 |  |
| truncated | bool | required | - | 제한 적용 여부 |  |

#### `PerformanceRiskSignals`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| table_count | int | required | - | 테이블 수 |  |
| has_writes | bool | required | - | 쓰기 여부 |  |
| uses_transaction | bool | required | - | 트랜잭션 |  |
| cyclomatic_complexity | int | required | - | 순환 복잡도 |  |
| has_cursor | bool | required | - | 커서 |  |
| has_dynamic_sql | bool | required | - | 동적 SQL |  |

#### `PerformanceRiskFinding`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 탐지 ID |  |
| severity | string | required | - | 심각도 |  |
| title | string | required | - | 제목 |  |
| markers | array[string] | required | - | 마커 | 정렬/중복 제거 |
| recommendation | string | required | - | 권장사항 |  |

#### `PerformanceRiskRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 메시지 |  |

#### `PerformanceRiskResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | PerformanceRiskObject | required | - | 대상 정보 |  |
| summary | PerformanceRiskSummary | required | - | 요약 |  |
| signals | PerformanceRiskSignals | required | - | 신호 |  |
| findings | array[PerformanceRiskFinding] | required | - | 탐지 항목 |  |
| recommendations | array[PerformanceRiskRecommendation] | required | - | 권장사항 |  |
| errors | array[string] | required | - | 에러 |  |

### DB Dependency

#### `DbDependencyOptions`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dialect | string | optional | "tsql" | 파서 dialect |  |
| case_insensitive | bool | optional | true | 대소문자 무시 |  |
| schema_sensitive | bool | optional | false | 스키마 민감도 |  |
| max_items | int | optional | 200 | 최대 항목 |  |

#### `DbDependencyRequest`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |
| sql | string | required | - | SQL |  |
| options | DbDependencyOptions | optional | defaults | 옵션 |  |

#### `DbDependencyObject`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 객체 이름 |  |
| type | string | required | - | 객체 유형 |  |

#### `DbDependencySummary`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| dependency_score | int | required | - | 의존도 점수 |  |
| dependency_level | string | required | - | 의존도 레벨 |  |
| truncated | bool | required | - | 제한 적용 여부 |  |

#### `DbDependencyMetrics`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| table_count | int | required | - | 테이블 수 |  |
| function_call_count | int | required | - | 함수 호출 수 |  |
| cross_database_count | int | required | - | 크로스 DB 수 |  |
| linked_server_count | int | required | - | 링크드 서버 수 |  |
| remote_exec_count | int | required | - | 원격 실행 수 |  |
| openquery_count | int | required | - | OPENQUERY 수 |  |
| opendatasource_count | int | required | - | OPENDATASOURCE 수 |  |
| system_proc_count | int | required | - | 시스템 프로시저 수 |  |
| xp_cmdshell_count | int | required | - | xp_cmdshell 수 |  |
| clr_signal_count | int | required | - | CLR 신호 수 |  |
| tempdb_pressure_signals | int | required | - | tempdb 신호 수 |  |

#### `DbDependencyCrossDatabaseItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| database | string | required | - | DB |  |
| schema | string | required | - | 스키마 | 필드명은 `alias="schema"` |
| object | string | required | - | 오브젝트 |  |
| kind | string | required | - | 종류 |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencyLinkedServerItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| name | string | required | - | 서버명 |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencyRemoteExecItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| target | string | required | - | 대상 |  |
| kind | string | required | - | 종류 |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencyExternalAccessItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | ID |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencySystemObjectItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | ID |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencyTempdbSignalItem`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | ID |  |
| signals | array[string] | required | - | 신호 |  |

#### `DbDependencyDependencies`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| cross_database | array[DbDependencyCrossDatabaseItem] | required | - | 크로스 DB | 정렬/캡 적용 |
| linked_servers | array[DbDependencyLinkedServerItem] | required | - | 링크드 서버 | 정렬/캡 적용 |
| remote_exec | array[DbDependencyRemoteExecItem] | required | - | 원격 실행 | 정렬/캡 적용 |
| external_access | array[DbDependencyExternalAccessItem] | required | - | 외부 접근 | 정렬/캡 적용 |
| system_objects | array[DbDependencySystemObjectItem] | required | - | 시스템 객체 | 정렬/캡 적용 |
| tempdb_signals | array[DbDependencyTempdbSignalItem] | required | - | tempdb 신호 | 정렬/캡 적용 |

#### `DbDependencyReason`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 사유 ID |  |
| weight | int | required | - | 가중치 |  |
| message | string | required | - | 메시지 |  |

#### `DbDependencyRecommendation`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| id | string | required | - | 권장 ID |  |
| message | string | required | - | 메시지 |  |

#### `DbDependencyResponse`
| Field | Type | Required | Default | Description | Notes |
| --- | --- | --- | --- | --- | --- |
| version | string | required | - | 응답 버전 |  |
| object | DbDependencyObject | required | - | 대상 정보 |  |
| summary | DbDependencySummary | required | - | 요약 |  |
| metrics | DbDependencyMetrics | required | - | 지표 |  |
| dependencies | DbDependencyDependencies | required | - | 의존성 상세 |  |
| reasons | array[DbDependencyReason] | required | - | 사유 |  |
| recommendations | array[DbDependencyRecommendation] | required | - | 권장사항 |  |
| errors | array[string] | required | - | 에러 |  |

---

## Testing
- **헬스 스모크**: `/health`가 `{ "status": "ok" }`를 반환하는지 확인.
- **no-SQL-echo 회귀**: 응답에 원문 SQL이 포함되지 않는지 검사.
- **결정론 스모크**: 동일 입력에 대해 동일한 정렬/캡 결과가 유지되는지 검사.
- **엔드포인트 별 테스트**: 각 `/mcp/*` 엔드포인트의 기본 응답 구조와 주요 필드 검증.

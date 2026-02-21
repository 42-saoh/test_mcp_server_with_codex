# Standardize Tags Catalog
(작성 규칙: 각 TAG 섹션은 빈 줄 없이 작성. 헤더 다음 줄에 바로 Summary/Keywords.)

## has_writes
Keywords: has_writes write_ops insert update delete merge
Summary: SQL 내부에서 쓰기 작업(INSERT/UPDATE/DELETE/MERGE 등)이 감지됨.
Why: 서비스 트랜잭션 경계/격리 수준/리플리케이션/감사 로깅에 직접 영향.
Do: 쓰기 작업을 명확히 분리(커맨드/쿼리 분리 가능하면), 트랜잭션 경계를 서비스 레이어로 이동 고려.
Evidence tips: spec.transactions / spec.data_changes 에서 쓰기 신호와 op 종류를 확인.

## read_only
Keywords: read_only no_txn
Summary: 쓰기 작업이 없고(read-only), 트랜잭션을 강제할 필요가 낮음.
Do: @Transactional(readOnly=true) 고려, 불필요한 락/격리수준 상향 금지.

## uses_transaction
Keywords: uses_transaction transaction transactional begin commit rollback
Summary: SQL 내부에서 명시적 트랜잭션 사용이 감지됨.
Do: 가능한 서비스 레이어 @Transactional로 승격(PAT_SERVICE_LAYER_TX 참고).
Related pattern: PAT_SERVICE_LAYER_TX

## no_txn
Keywords: no_txn read_only
Summary: SQL 내부에서 트랜잭션 신호가 약하거나 없음.
Do: 기본은 트랜잭션 없이 시작하되, 쓰기/일관성 요구가 있으면 서비스 레이어에서 부여.

## dynamic_sql
Keywords: dynamic_sql IMP_DYN_SQL TPL_DYNAMIC_* PAT_MYBATIS_DYNAMIC_TAGS mybatis if choose foreach
Summary: 동적 SQL 생성(문자열 연결/조건 분기)이 감지됨.
Do: MyBatis 동적 태그(<if>/<choose>/<foreach>)로 모델링. 바인딩 파라미터로 SQL injection 위험 감소.
Related impact: IMP_DYN_SQL
Related pattern: PAT_MYBATIS_DYNAMIC_TAGS

## cursor
Keywords: cursor IMP_CURSOR PAT_REPLACE_CURSOR_SET_BASED set based set-based
Summary: 커서 사용 감지됨.
Do: set-based 쿼리 또는 배치 처리로 치환.
Related impact: IMP_CURSOR
Related pattern: PAT_REPLACE_CURSOR_SET_BASED

## temp_objects
Keywords: temp_objects IMP_TEMP_TABLE IMP_TABLE_VARIABLE temp table table variable #temp
Summary: 임시 테이블/테이블 변수 사용 감지됨.
Do: 가능하면 CTE/파생 테이블/앱 메모리 구조로 대체. 임시객체는 트랜잭션/동시성 영향 고려.

## merge
Keywords: merge IMP_MERGE upsert
Summary: MERGE 사용 감지됨.
Do: 대상 DB/ORM/프레임워크에서 UPSERT 전략을 표준화(경쟁 조건, 동시성, 트리거 영향 포함).

## linked_server
Keywords: linked_server openquery opendatasource four-part-name external integration
Summary: Linked Server 의존성 감지됨.
Do: 통합 어댑터 계층으로 격리(PAT_ISOLATE_EXTERNAL_INTEGRATION 참고).
Related pattern: PAT_ISOLATE_EXTERNAL_INTEGRATION

## cross_db
Keywords: cross_db database.schema.object three-part-name external integration
Summary: Cross-DB 접근 감지됨.
Do: 데이터 소유권/동기화 전략/조회 복제/CDC 등 아키텍처 결정을 문서화 후 코드 표준 적용.
Related pattern: PAT_ISOLATE_EXTERNAL_INTEGRATION

## low_complexity
Keywords: low_complexity cyclomatic_complexity
Summary: 순환 복잡도 낮음.
Do: 단순 매핑(rewrite/translate) 우선, 테스트 케이스 중심으로 검증.

## high_complexity
Keywords: high_complexity cyclomatic_complexity
Summary: 순환 복잡도 높음.
Do: 규칙/분기 단위로 분해, 단위 테스트+골든 결과 기반 검증 강화.

## perf_risk_high
Keywords: perf_risk_high performance risk
Summary: 성능 리스크가 높게 평가됨.
Do: 인덱스/쿼리 플랜/카디널리티/페이징 전략 포함해서 별도 튜닝 문서 필요.

## difficulty_high
Keywords: difficulty_high mybatis difficulty
Summary: MyBatis 변환 난이도가 높게 평가됨.
Do: 템플릿 적용(TPL_*) 우선, 파라미터/결과 매핑 규칙을 표준화하고 리팩토링 단계를 쪼갠다.
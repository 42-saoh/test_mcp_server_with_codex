---
applyTo: "**/MIGRATION_GUIDE.md"
---

# 목적
- 1차 목표: “의존성 인벤토리”를 확정(Confirmed) 수준으로 최대한 상세화한다.
- 2차 목표: “SP 복잡도 분석”을 정량/정성으로 심층화한다.
- 3차 목표: “근거 기반”으로 만들기 위해 DB에서 추출할 수 있는 실행 가능한 SQL 쿼리를 문서에 포함한다.

# 필수 산출물
- 최종 출력은 **MIGRATION_GUIDE.md 전체 최신본(기존 내용 유지 + 보강)** 이어야 한다.
- 문서 내 모든 표/요약은 반드시 아래의 상태를 명시한다:
  - Confirmed(확정): 실제 정의/카탈로그/분석 근거로 확인됨
  - Needs verification(추출대기/의심): 정적 분석 한계/동적 SQL/환경 미확인 등으로 확정 불가

# 작업 범위 제한 (필수 준수)
✅ 해야 할 것
- MIGRATION_GUIDE.md 생성 또는 업데이트
- 추출 결과가 불확실하면 반드시 Needs verification으로 표기하고 “무엇을 더 추출하면 확정되는지”를 함께 적는다.

❌ 하지 말 것
- Java/Spring/MyBatis 코드 생성
- DTO/Mapper/XML 생성
- “완료”라고 단정 (추출대기는 추출대기라고 명시)

---

## 1) 1차 목표: “의존성 인벤토리” 상세화

### 1.1 SP/FN/테이블/뷰/시스템객체 의존성 목록
MIGRATION_GUIDE.md에 아래를 반드시 추가/보강한다.

- 확정(Confirmed) 과 추출대기/의심(Needs verification)을 **명확히 분리해서 표로 정리**
- 최소 포함 항목:
  - 참조 테이블/뷰
  - 호출 UDF/TVF
  - 호출 Stored Procedure (EXEC, INSERT-EXEC 포함)
  - 동적 SQL(sp_executesql, EXEC(@sql)) 여부 및 후보 문자열
  - 링크드 서버/OPENQUERY/4-part name 등 외부 참조 여부
  - 임시테이블(#temp), 테이블변수(@table) 목록과 스키마(컬럼)까지 가능한 범위로 정리

표 템플릿(필요 시 확장):

#### Confirmed
| Type | Name | How referenced | Evidence | Notes |
|---|---|---|---|---|

#### Needs verification
| Type | Name/Candidate | Why uncertain | What to extract next | Notes |
|---|---|---|---|---|

### 1.2 “DML 영향도 매트릭스” (테이블별 변경)
- 테이블별로 SELECT/INSERT/UPDATE/DELETE/MERGE 여부를 매트릭스로 표시
- INSERT/UPDATE 대상은 키 컬럼/조건/중요 컬럼 요약
- DB(예: PPM/ERP 등) 별로 분리해서 정리

표 템플릿(DB별 섹션 반복):

| Table | SELECT | INSERT | UPDATE | DELETE | MERGE | Keys/Join/Where 요약 | 중요 컬럼/값 패턴 | Evidence |
|---|---:|---:|---:|---:|---:|---|---|---|

### 1.3 호출 흐름(콜 그래프) 서술
- “입력 파라미터 → 주요 단계(phase) → 데이터 변경 → 외부 반영 → 결과/에러처리”
- 가능한 경우 단계별로 “읽는 테이블/쓰는 테이블/호출 함수” 포함

템플릿:

#### Call flow
1) Inputs
- ...

2) Phase A: ...
- Reads: ...
- Writes: ...
- Calls: ...

3) Phase B: ...
...

4) Results / Output
- ...

5) Error handling
- ...

---

## 2) 2차 목표: “SP 복잡도 분석” 심층화

### 2.1 정량 메트릭(가능한 한 실제 계산)
가능하면 실제 SP 정의를 기반으로 카운트해서 표로 제시한다.

- LOC(라인 수)
- BEGIN/END 블록 수
- IF/ELSE 수
- WHILE/LOOP 수
- CASE 수
- GOTO/RETURN 수
- CURSOR 수 (OPEN/FETCH/CLOSE/DEALLOCATE 포함)
- TRY/CATCH 여부(있다면 블록 수)
- 트랜잭션(BEGIN TRAN/COMMIT/ROLLBACK) 사용 여부
- 동적 SQL 사용 여부
- 크로스DB 참조 개수 (예: ERP.dbo.Table, PPM.dbo.Table)

표 템플릿:

| Metric | Count | Evidence/Rule | Notes |
|---|---:|---|---|

### 2.2 제어흐름(Control Flow) 리스크 분석
- 에러 처리 패턴: @@ERROR, GOTO ERRORHANDLER, RAISERROR/THROW 등
- “정상 종료 / 예외 종료 / 자원 정리” 분기 위치를 글로 명확히 설명
- Java 전환 매핑 제안: try-catch-finally, 예외 계층, 롤백 정책(트랜잭션 경계 포함)

### 2.3 데이터 정합성/동시성 리스크
- 번호채번/전표생성/자산등록이 재실행(idempotent)에 안전한지
- 동시 실행 시 중복/경합 포인트(채번 함수, UNIQUE 키, MAX+1 패턴 등)
- 락/격리수준 힌트 분석 (UPDLOCK, HOLDLOCK, SERIALIZABLE, sp_getapplock 등)

### 2.4 크로스DB 트랜잭션 리스크
- PPM↔ERP가 같은 인스턴스/다른 인스턴스일 때 리스크를 분리해 설명
- 분산 트랜잭션이 불가능할 때 보상 트랜잭션(역분개/취소) 전략을 문서에 제안

---

## 3) “근거 기반”: DB에서 추출하는 쿼리 포함(실행 가능한 형태)

MIGRATION_GUIDE.md에 아래 섹션을 추가하고, 각 쿼리 아래에 “결과 붙여넣기” 표 템플릿을 둔다.

### 3.1 SP 정의 추출
- sys.sql_modules
- OBJECT_DEFINITION(OBJECT_ID(...))

### 3.2 정적 의존성
- sys.sql_expression_dependencies
- sys.dm_sql_referenced_entities

### 3.3 동적 SQL 탐지(정규식/LIKE 기반)
- sp_executesql, EXEC(, OPENQUERY, LinkedServer 등 키워드 스캔

### 3.4 테이블변수/임시테이블 스키마 추정(가능한 범위)
- DECLARE @t TABLE (...) 파싱
- CREATE TABLE #t (...) 파싱

각 쿼리는 “복사해서 SSMS에서 바로 실행” 가능한 형태로 제공한다.

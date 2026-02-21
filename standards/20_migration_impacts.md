# Migration Impacts Catalog (IMP_*)

## IMP_DYN_SQL
Keywords: IMP_DYN_SQL dynamic_sql PAT_MYBATIS_DYNAMIC_TAGS mybatis if choose foreach
Summary: 동적 SQL(문자열 연결/조건 분기)이 포함되어 마이그레이션 시 구조 재설계가 필요.
Risk: SQL Injection 위험, 캐시/플랜 안정성 저하, 테스트 케이스 폭증.
Do: MyBatis <if>/<choose>/<foreach>로 조건/리스트를 모델링하고, 값은 바인딩 파라미터로 전달.
Don't: SQL 문자열을 코드에서 CONCAT해서 실행하지 않는다.
Example (Bad): "WHERE " + col + " = " + value
Example (Good): <if test="value != null">WHERE col = #{value}</if>
Related: dynamic_sql, TPL_DYNAMIC_*, PAT_MYBATIS_DYNAMIC_TAGS

## IMP_CURSOR
Keywords: IMP_CURSOR cursor PAT_REPLACE_CURSOR_SET_BASED set based set-based
Summary: 커서 기반 로직으로 인해 set-based 쿼리로 치환 작업이 필요.
Do: 집합 연산/윈도우 함수/CTE/배치 처리로 변환. 업무 규칙을 “테이블 변환 규칙”으로 재기술.
Related: cursor, PAT_REPLACE_CURSOR_SET_BASED

## IMP_TEMP_TABLE
Keywords: IMP_TEMP_TABLE temp_objects temp table #temp
Summary: 임시 테이블(#temp) 사용. 실행 계획/통계/트랜잭션 스코프 영향을 고려해야 함.
Do: 가능하면 CTE/파생테이블로 대체. 유지 시 생성/인덱스/정리 전략을 표준화.

## IMP_TABLE_VARIABLE
Keywords: IMP_TABLE_VARIABLE temp_objects table variable
Summary: 테이블 변수 사용. 카디널리티 추정 한계로 성능 이슈가 날 수 있음.
Do: 대체 가능하면 temp table/CTE로 변경. 유지 시 row count/인덱스 전략을 문서화.

## IMP_MERGE
Keywords: IMP_MERGE merge upsert
Summary: MERGE 기반 UPSERT. 동시성/경쟁 조건/트리거에 민감.
Do: UPSERT 표준(낙관/비관 락, 유니크 키, 충돌 처리)을 팀 표준으로 정하고 동일 패턴으로 치환.
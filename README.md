# MSSQL Migration MCP Server (Python)

MSSQL Stored Procedure / Function을 분석하고, Java + Spring Boot + MyBatis 마이그레이션을 표준화/자동화하기 위한 **MCP(Model Context Protocol) 서버**입니다.  
VS Code에서 GitHub Copilot과 연동하여 SP/FN 분석 결과, 변환 가이드, RAG 기반 참고 자료를 툴 형태로 제공하는 것을 목표로 합니다.

---

## 주요 기능

### 1) SP/FN 분석
- SP/FN 에 사용하고 있는 함수 및 테이블 추출
- 트랜잭션 패턴 분석 (BEGIN/COMMIT/ROLLBACK, TRY/CATCH)
- 마이그레이션 영향 로직 탐지 (CURSOR, 동적 SQL, 임시테이블, MERGE 등)
- 제어 흐름 분석 (IF/WHILE/CASE/RETURN)
- 데이터 변경 유형 분류 (SELECT/INSERT/UPDATE/DELETE/MERGE)
- 에러/예외 처리 패턴 분석

### 2) 공통 기능 후보 판별
- 해당 SP/FN을 호출하는 다른 SP/FN 존재 여부 및 호출 수 확인
- 외부 의존성 패턴 감지 (linked server, cross-DB, OPENQUERY/OPENDATASOURCE, EXEC AT, CLR/xp_cmdshell)
- 재사용/확장 가능성(유틸화 가능성) 평가
- 비즈니스 규칙 추출 및 표준 템플릿 매핑
- 호출 그래프(Call Graph) 생성
- 공통화 위험도 스코어링

### 3) 마이그레이션 설계 지원
- Java/MyBatis 매핑 전략 추천
- 트랜잭션 경계 제안
- MyBatis 변환 난이도 평가

### 4) 품질/운영 지원
- 성능 리스크 탐지
- DB 의존도 점수

### 5) RAG 기반 표준화(옵션)
- 사내 표준 문서/가이드, 변환 규칙, 예제 코드 등을 인덱싱
- 분석 결과와 함께 근거 문서/권장 패턴을 함께 반환

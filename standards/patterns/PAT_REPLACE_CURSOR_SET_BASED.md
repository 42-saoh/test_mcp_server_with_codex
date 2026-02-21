# PAT_REPLACE_CURSOR_SET_BASED
Keywords: PAT_REPLACE_CURSOR_SET_BASED cursor set based set-based IMP_CURSOR
Summary: 커서를 set-based 쿼리 또는 배치 처리로 치환한다.
Approach: (1) 커서가 만드는 “중간 결과”를 테이블로 정의 (2) 집합 연산/윈도우 함수로 변환 (3) 배치 처리 시 paging 기준 정의
# PAT_AVOID_SELECT_STAR
Keywords: PAT_AVOID_SELECT_STAR select columns explicit SELECT_STAR
Summary: SELECT *를 피하고 명시적 컬럼 리스트를 사용한다.
Why: 스키마 변경에 취약, 네트워크/IO 증가, 결과 매핑 오류 유발.
Do: 필요한 컬럼만 선택 + ResultMap/DTO와 1:1 매핑
Note: 성능/리스크 ID가 *_SELECT_STAR 형태로 나오면 이 문서가 증거로 붙게끔 관련 ID도 함께 기록 권장.
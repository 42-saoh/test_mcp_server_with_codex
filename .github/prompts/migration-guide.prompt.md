---
name: migration-guide
description: Generate/refresh MIGRATION_GUIDE.md (dependency inventory + complexity + evidence queries)
agent: agent
argument-hint: "대상 SP/FN 이름, DB명, 또는 입력 파일 경로 등을 적어줘 (예: db=PPM sp=dbo.usp_xxx)"
---

다음 규칙을 최우선으로 적용해 MIGRATION_GUIDE.md를 생성/업데이트해줘:
- 지침 파일: ../instructions/migration-guide.instructions.md (반드시 준수)
- ✅ 해야 할 것: MIGRATION_GUIDE.md 전체 최신본 출력(기존 내용 유지 + 보강)
- ❌ 하지 말 것: Java/Spring/MyBatis 코드/DTO/Mapper/XML 생성, “완료” 단정

작업 방법:
1) 가능한 경우 MCP 도구/DB 메타데이터/소스 분석으로 근거를 확보해 “Confirmed”를 늘리고,
2) 확정 불가한 항목은 “Needs verification”으로 분리하고, 무엇을 추가로 추출해야 확정되는지까지 적어줘.
3) 문서에 “실행 가능한 SQL 추출 쿼리” 섹션과 “결과 붙여넣기 표 템플릿”을 포함해줘.

입력으로 제공된 대상(예: SP/FN 이름/파일/DB)을 중심으로 작성해줘.

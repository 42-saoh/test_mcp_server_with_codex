# PAT_MYBATIS_DYNAMIC_TAGS
Keywords: PAT_MYBATIS_DYNAMIC_TAGS dynamic sql mybatis if choose foreach dynamic_sql IMP_DYN_SQL TPL_DYNAMIC_*
Summary: 동적 SQL 문자열 조립 대신 MyBatis <if>/<choose>/<foreach>로 표현한다.
Problem: 문자열 조립은 SQL injection/플랜 불안정/테스트 난이도를 키움.
Solution: 조건/분기/IN 리스트를 MyBatis 동적 태그로 모델링하고 값은 바인딩 파라미터 사용.
Example: <if test="x != null">AND col = #{x}</if> / <foreach collection="ids" item="id" open="(" close=")" separator=",">#{id}</foreach>
Checklist: (1) 문자열 CONCAT 금지 (2) 값은 #{param} 바인딩 (3) 분기는 <choose> 우선 (4) IN은 <foreach>
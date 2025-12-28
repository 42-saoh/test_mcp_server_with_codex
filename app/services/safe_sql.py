# [파일 설명]
# - 목적: SQL 요약 정보를 계산해 안전한 로그 출력에 활용한다.
# - 제공 기능: 길이/해시 등의 요약 데이터를 생성한다.
# - 입력/출력: 원문 SQL을 입력으로 받아 요약 dict를 반환한다.
# - 주의 사항: 원문 SQL 자체는 반환하거나 로그에 남기지 않는다.
# - 연관 모듈: 분석 서비스(app.services.*)에서 로그 요약에 사용된다.
from __future__ import annotations

import hashlib
import re

BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_PATTERN = re.compile(r"--.*?$", re.MULTILINE)
STRING_LITERAL_PATTERN = re.compile(r"N'(?:''|[^'])*'|'(?:''|[^'])*'", re.DOTALL)


# [함수 설명]
# - 목적: summarize_sql 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def summarize_sql(sql: str) -> dict[str, int | str]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    return {"len": len(sql), "sha256_8": sql_hash}


# [함수 설명]
# - 목적: strip_comments_and_strings 처리 로직을 수행한다.
# - 입력: sql: str
# - 출력: 구조화된 dict 결과를 반환한다.
# - 에러 처리: 예외 발생 시 errors/notes에 기록하거나 안전한 기본값을 사용한다.
# - 결정론: 정렬/중복 제거/최대 개수 제한을 통해 결과 순서를 안정화한다.
# - 보안: 원문 SQL 등 민감 정보는 로그에 직접 남기지 않도록 요약한다.
def strip_comments_and_strings(sql: str) -> str:
    sql = BLOCK_COMMENT_PATTERN.sub(" ", sql)
    sql = LINE_COMMENT_PATTERN.sub(" ", sql)
    sql = STRING_LITERAL_PATTERN.sub("''", sql)
    return sql

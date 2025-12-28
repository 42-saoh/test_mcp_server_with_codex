from __future__ import annotations

import hashlib
import re

BLOCK_COMMENT_PATTERN = re.compile(r"/\*.*?\*/", re.DOTALL)
LINE_COMMENT_PATTERN = re.compile(r"--.*?$", re.MULTILINE)
STRING_LITERAL_PATTERN = re.compile(r"N'(?:''|[^'])*'|'(?:''|[^'])*'", re.DOTALL)


def summarize_sql(sql: str) -> dict[str, int | str]:
    sql_hash = hashlib.sha256(sql.encode("utf-8")).hexdigest()[:8]
    return {"len": len(sql), "sha256_8": sql_hash}


def strip_comments_and_strings(sql: str) -> str:
    sql = BLOCK_COMMENT_PATTERN.sub(" ", sql)
    sql = LINE_COMMENT_PATTERN.sub(" ", sql)
    sql = STRING_LITERAL_PATTERN.sub("''", sql)
    return sql

# Performance Risk Catalog (PRF_*)

## Overview
Performance risk IDs appear under `spec.risks.performance`.

## When to use / Why it matters
Use these IDs to prioritize query optimization and migration-safe refactoring.

## Identifiers (explicit tokens)
- tags: perf_risk_high, cursor, dynamic_sql, temp_objects
- risk_ids: PRF_SELECT_STAR, PRF_LEADING_WILDCARD_LIKE, PRF_FUNCTION_ON_COLUMN, PRF_CURSOR_RBAR, PRF_NOLOCK, PRF_NO_WHERE_ON_UPDATE, PRF_NO_WHERE_ON_DELETE, PRF_POSSIBLE_NO_WHERE_UPDATE, PRF_POSSIBLE_NO_WHERE_DELETE, PRF_DYNAMIC_SQL, PRF_LOOP_RBAR, PRF_SELECT_INTO, PRF_MERGE, PRF_IMPLICIT_CONVERSION_HINT, PRF_OR_CHAIN, PRF_IN_LIST_LARGE, PRF_SCALAR_UDF, PRF_TABLE_VARIABLE, PRF_TEMP_TABLE, PRF_ORDER_BY_NO_TOP
- template_ids: TPL_VALIDATE_RANGE
- pattern_ids: PAT_AVOID_SELECT_STAR, PAT_REPLACE_CURSOR_SET_BASED, PAT_MYBATIS_DYNAMIC_TAGS

## Guidance / Patterns
- PRF_SELECT_STAR: use explicit projection and `PAT_AVOID_SELECT_STAR`.
- PRF_CURSOR_RBAR, PRF_LOOP_RBAR: replace row-by-row loops with set-based operations.
- PRF_DYNAMIC_SQL: parameterize and structure dynamic conditions.
- PRF_NO_WHERE_ON_UPDATE, PRF_NO_WHERE_ON_DELETE: enforce predicates and safe guards.
- PRF_TABLE_VARIABLE, PRF_TEMP_TABLE: control cardinality and tempdb pressure.
- PRF_SCALAR_UDF, PRF_FUNCTION_ON_COLUMN: avoid non-sargable filters.

## Examples
- Pseudo example: replace `select *` with DTO-specific column list.
- Pseudo example: split large IN list into staged table plus indexed join.

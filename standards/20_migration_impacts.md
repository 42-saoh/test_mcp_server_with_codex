# Migration Impacts Catalog (IMP_*)

## Overview
This document defines migration impact identifiers used by `spec.risks.migration_impacts`.

## When to use / Why it matters
Use these impact IDs when planning Java + Spring Boot + MyBatis migration steps and review scope.

## Identifiers (explicit tokens)
- tags: dynamic_sql, cursor, temp_objects, merge, linked_server
- risk_ids: IMP_DYN_SQL, IMP_CURSOR, IMP_LINKED_SERVER, IMP_SYSTEM_PROC, IMP_TEMP_TABLE, IMP_TABLE_VARIABLE, IMP_MERGE, IMP_OUTPUT_CLAUSE, IMP_IDENTITY, IMP_NONDETERMINISM, IMP_ERROR_SIGNALING
- template_ids: TPL_VALIDATE_REQUIRED_PARAM, TPL_VALIDATE_RANGE, TPL_ENSURE_EXISTS, TPL_ENSURE_NOT_EXISTS, TPL_SOFT_DELETE_FILTER, TPL_STATUS_FILTER, TPL_CASE_TO_ENUM_MAPPING, TPL_ERROR_TO_EXCEPTION
- pattern_ids: PAT_MYBATIS_DYNAMIC_TAGS, PAT_REPLACE_CURSOR_SET_BASED, PAT_ISOLATE_EXTERNAL_INTEGRATION

## Guidance / Patterns
### IMP_DYN_SQL
Use `PAT_MYBATIS_DYNAMIC_TAGS` and parameter binding for dynamic SQL migration.

### IMP_CURSOR
Prefer set-based transformation and `PAT_REPLACE_CURSOR_SET_BASED`.

### IMP_LINKED_SERVER
Isolate external integration and apply `PAT_ISOLATE_EXTERNAL_INTEGRATION`.

### IMP_SYSTEM_PROC
Review system-specific procedures and replace with portable service logic.

### IMP_TEMP_TABLE / IMP_TABLE_VARIABLE
Evaluate tempdb pressure and replace with CTE, batching, or domain collections.

### IMP_MERGE
Define deterministic upsert strategy and transaction handling.

### IMP_OUTPUT_CLAUSE
Capture generated values with explicit return mapping in service layer.

### IMP_IDENTITY
Use generated-key handling strategy instead of implicit identity reads.

### IMP_NONDETERMINISM
Stabilize time/random dependencies for deterministic tests.

### IMP_ERROR_SIGNALING
Map SQL error signaling to application exceptions consistently.

## Examples
- Pseudo example: dynamic conditions use MyBatis `<if>` and `<foreach>` instead of string concatenation.
- Pseudo example: cursor loop replaced by set-based update and batched service invocation.

# Template Catalog (TPL_*)

## Overview
Template IDs represent reusable business-rule migration shapes.

## When to use / Why it matters
Use template IDs in `spec.templates[].id` to standardize mapper/service implementation plans.

## Identifiers (explicit tokens)
- tags: dynamic_sql, uses_transaction, has_writes
- risk_ids: IMP_DYN_SQL, IMP_ERROR_SIGNALING
- template_ids: TPL_VALIDATE_REQUIRED_PARAM, TPL_VALIDATE_RANGE, TPL_ENSURE_EXISTS, TPL_ENSURE_NOT_EXISTS, TPL_SOFT_DELETE_FILTER, TPL_STATUS_FILTER, TPL_CASE_TO_ENUM_MAPPING, TPL_ERROR_TO_EXCEPTION
- pattern_ids: PAT_MYBATIS_DYNAMIC_TAGS, PAT_SERVICE_LAYER_TX

## Guidance / Patterns
- TPL_VALIDATE_REQUIRED_PARAM: required-parameter null/empty guard.
- TPL_VALIDATE_RANGE: bounded numeric/date range guard.
- TPL_ENSURE_EXISTS: existence precondition check.
- TPL_ENSURE_NOT_EXISTS: uniqueness precondition check.
- TPL_SOFT_DELETE_FILTER: reusable active-row predicate.
- TPL_STATUS_FILTER: status-based filtering policy.
- TPL_CASE_TO_ENUM_MAPPING: CASE-based code-to-enum mapping.
- TPL_ERROR_TO_EXCEPTION: RAISERROR/THROW to exception translation.

## Examples
- Pseudo example: validation templates applied before mapper invocation.
- Pseudo example: CASE mapping centralized in enum conversion utility.

# DB Dependency Catalog

## Overview
This document defines dependency-risk identifiers from `spec.risks.db_dependency`.

## When to use / Why it matters
Use these IDs to identify coupling across linked servers, cross-database calls, and SQL Server-only features.

## Identifiers (explicit tokens)
- tags: linked_server, cross_db
- risk_ids: RSN_LINKED_SERVER, RSN_CROSS_DB, RSN_REMOTE_EXEC, RSN_OPENQUERY, RSN_OPENDATASOURCE, RSN_XP_CMDSHELL, RSN_SYSTEM_PROC, RSN_CLR, RSN_TEMPDB
- template_ids: TPL_ERROR_TO_EXCEPTION
- pattern_ids: PAT_ISOLATE_EXTERNAL_INTEGRATION

## Guidance / Patterns
- RSN_LINKED_SERVER, RSN_OPENQUERY, RSN_OPENDATASOURCE: isolate through adapters and explicit contracts.
- RSN_CROSS_DB, RSN_REMOTE_EXEC: decouple with API calls, CDC, or read-model replication.
- RSN_XP_CMDSHELL, RSN_SYSTEM_PROC, RSN_CLR: remove platform-specific execution paths.
- RSN_TEMPDB: reduce temporary object pressure and monitor tempdb hotspots.

## Examples
- Pseudo example: integration adapter handles remote data access with timeout/retry policies.
- Pseudo example: cross_db reads replaced with synchronized projection tables.

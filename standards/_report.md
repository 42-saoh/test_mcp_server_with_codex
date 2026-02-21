# Standards Coverage Report

Generated at: 2026-02-21T12:52:02.791723+00:00
Docs directory: standards
Chunk count: 62

## Coverage Summary

| Category | Total | Covered | Missing | Ambiguous |
|---|---:|---:|---:|---:|
| tags | 14 | 14 | 0 | 0 |
| risk_ids | 40 | 40 | 0 | 0 |
| template_ids | 8 | 8 | 0 | 0 |
| pattern_ids | 5 | 5 | 0 | 0 |
| pattern_keywords | 23 | 23 | 0 | 0 |

## Missing Identifiers

| Category | Identifier | Recommended doc target |
|---|---|---|

## Notes

- Coverage uses `app.services.rag_lexical.load_documents` chunking behavior.
- Query-term tokenization splits identifiers on `_`, `-`, and `.`; include exact IDs and useful split keywords in docs.
- `ambiguous` means identifier appears only in headings or file names (or heading-only chunks), which may reduce retrieval quality.

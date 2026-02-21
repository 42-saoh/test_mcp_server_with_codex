from app.services.rag_lexical import extract_query_terms


def test_extract_query_terms_splits_compound_terms() -> None:
    spec = {
        "tags": ["dynamic_sql", "read_only"],
        "templates": [{"id": "TPL_DYNAMIC_SQL"}],
        "risks": {"migration_impacts": ["IMP_DYN_SQL"], "performance": [], "db_dependency": []},
    }

    terms = extract_query_terms(spec)

    assert "dynamic_sql" in terms
    assert "dynamic" in terms
    assert "sql" in terms
    assert "read_only" not in terms

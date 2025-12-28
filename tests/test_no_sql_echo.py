from fastapi.testclient import TestClient

from app.main import app

SENTINEL = "SQL_SENTINEL__FROM_DBO"


def test_no_sql_echo_analyze() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/analyze",
        json={
            "sql": f"SELECT * FROM dbo.Users WHERE note = '{SENTINEL}';",
            "dialect": "tsql",
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text


def test_no_sql_echo_standardize_spec() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/standardize/spec",
        json={
            "object": {"name": "dbo.usp_NoEcho", "type": "procedure"},
            "sql": f"CREATE PROCEDURE dbo.usp_NoEcho AS SELECT '{SENTINEL}';",
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text


def test_no_sql_echo_standardize_spec_with_evidence(tmp_path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "placeholder.md").write_text(
        "# Placeholder Doc\n\nUse documented patterns for migrations.",
        encoding="utf-8",
    )

    client = TestClient(app)
    response = client.post(
        "/mcp/standardize/spec-with-evidence",
        json={
            "object": {"name": "dbo.usp_NoEchoEvidence", "type": "procedure"},
            "sql": f"CREATE PROCEDURE dbo.usp_NoEchoEvidence AS SELECT '{SENTINEL}';",
            "options": {"docs_dir": str(docs_dir), "top_k": 3},
        },
    )

    assert response.status_code == 200
    assert SENTINEL not in response.text

from fastapi.testclient import TestClient

from app.main import app

SENTINEL = "SQL_PARSE_SENTINEL__FROM_DBO"
MALFORMED_SQL = f"SELECT '{SENTINEL}"


def test_mcp_analyze_parse_error_does_not_echo_sql() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/analyze",
        json={
            "sql": MALFORMED_SQL,
            "dialect": "tsql",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert any(error.startswith("parse_error:") for error in payload["errors"])
    assert SENTINEL not in response.text


def test_mcp_analyze_parse_error_is_deterministic() -> None:
    client = TestClient(app)
    request_payload = {"sql": MALFORMED_SQL, "dialect": "tsql"}

    first = client.post("/mcp/analyze", json=request_payload)
    second = client.post("/mcp/analyze", json=request_payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()

from fastapi.testclient import TestClient

from app.main import app


def test_rules_template_no_rules() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Simple",
            "type": "procedure",
            "sql": "CREATE PROCEDURE dbo.usp_Simple AS SELECT * FROM dbo.Users;",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["has_rules"] is False
    assert payload["summary"]["rule_count"] == 0
    assert payload["summary"]["template_suggestion_count"] == 0


def test_rules_template_guard_throw() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Guard",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Guard @p INT AS
            BEGIN
                IF @p IS NULL
                BEGIN
                    THROW 50000, 'missing', 1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["has_rules"] is True
    assert payload["summary"]["rule_count"] == 1
    rule = payload["rules"][0]
    assert rule["kind"] == "guard_clause"
    assert rule["action"] == "raise_error"

    template_ids = {item["template_id"] for item in payload["template_suggestions"]}
    assert "TPL_VALIDATE_REQUIRED_PARAM" in template_ids
    assert "TPL_ERROR_TO_EXCEPTION" in template_ids


def test_rules_template_exists_raiserror() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Exists",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Exists @id INT AS
            BEGIN
                IF EXISTS (SELECT 1 FROM dbo.Users WHERE id = @id)
                BEGIN
                    RAISERROR('exists', 16, 1);
                    RETURN -1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    kinds = {rule["kind"] for rule in payload["rules"]}
    assert "exists_check" in kinds
    template_ids = {item["template_id"] for item in payload["template_suggestions"]}
    assert "TPL_ENSURE_EXISTS" in template_ids
    assert "TPL_ERROR_TO_EXCEPTION" in template_ids


def test_rules_template_ignores_comments_and_strings() -> None:
    client = TestClient(app)

    response = client.post(
        "/mcp/common/rules-template",
        json={
            "name": "dbo.usp_Comments",
            "type": "procedure",
            "sql": """
            CREATE PROCEDURE dbo.usp_Comments @p INT AS
            BEGIN
                -- IF EXISTS (SELECT 1 FROM dbo.Table)
                SELECT 'IF @p IS NULL THEN THROW' AS Note;
                IF @p IS NULL
                BEGIN
                    RETURN 1;
                END
            END
            """,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["rule_count"] == 1
    kinds = {rule["kind"] for rule in payload["rules"]}
    assert kinds == {"guard_clause"}

from fastapi.testclient import TestClient

from app.main import app


def test_mcp_analyze_error_handling_simple() -> None:
    client = TestClient(app)
    payload = {"sql": "SELECT 1", "dialect": "tsql"}

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    data = response.json()
    error_handling = data["error_handling"]
    assert error_handling["has_try_catch"] is False
    assert error_handling["try_count"] == 0
    assert error_handling["catch_count"] == 0
    assert error_handling["uses_throw"] is False
    assert error_handling["throw_count"] == 0
    assert error_handling["uses_raiserror"] is False
    assert error_handling["raiserror_count"] == 0
    assert error_handling["uses_at_at_error"] is False
    assert error_handling["at_at_error_count"] == 0
    assert error_handling["uses_error_functions"] == []
    assert error_handling["uses_print"] is False
    assert error_handling["print_count"] == 0
    assert error_handling["uses_return"] is False
    assert error_handling["return_count"] == 0
    assert error_handling["return_values"] == []
    assert error_handling["uses_output_error_params"] is False
    assert error_handling["output_error_params"] == []
    assert error_handling["signals"] == []


def test_mcp_analyze_error_handling_try_catch_throw() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        BEGIN TRY
            SELECT 1;
        END TRY
        BEGIN CATCH
            DECLARE @msg NVARCHAR(4000) = ERROR_MESSAGE();
            THROW;
        END CATCH
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    error_handling = response.json()["error_handling"]
    assert error_handling["has_try_catch"] is True
    assert error_handling["try_count"] == 1
    assert error_handling["catch_count"] == 1
    assert error_handling["uses_throw"] is True
    assert error_handling["throw_count"] >= 1
    assert "ERROR_MESSAGE" in error_handling["uses_error_functions"]
    assert "TRY/CATCH" in error_handling["signals"]
    assert "THROW" in error_handling["signals"]
    assert "ERROR_MESSAGE" in error_handling["signals"]


def test_mcp_analyze_error_handling_raiserror_ataterror_return() -> None:
    client = TestClient(app)
    payload = {
        "sql": """
        RAISERROR('bad', 16, 1);
        IF @@ERROR <> 0
            RETURN -1;
        """,
        "dialect": "tsql",
    }

    response = client.post("/mcp/analyze", json=payload)

    assert response.status_code == 200
    error_handling = response.json()["error_handling"]
    assert error_handling["uses_raiserror"] is True
    assert error_handling["raiserror_count"] >= 1
    assert error_handling["uses_at_at_error"] is True
    assert error_handling["at_at_error_count"] >= 1
    assert error_handling["uses_return"] is True
    assert -1 in error_handling["return_values"]
    assert "RAISERROR" in error_handling["signals"]
    assert "@@ERROR" in error_handling["signals"]
    assert "RETURN" in error_handling["signals"]

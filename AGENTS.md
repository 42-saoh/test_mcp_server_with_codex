# AGENTS.md (Codex Instructions)

This repository is a **Python FastAPI MCP server** for supporting **MSSQL SP/FN analysis + (optional) RAG** to standardize migrations to **Java + Spring Boot + MyBatis**.

Codex should follow the rules below for any change.

---

## 0) Non-negotiables

- **Do not require internet access at agent runtime.** Assume the agent execution phase may have no network.
- **Do not require real API keys for tests.** Any OpenAI / external calls must be **mocked** in unit tests.
- **Do not log secrets or full raw SQL** in tests or example outputs.
- Prefer minimal changes that keep endpoints stable.

---

## 1) Quick start commands (always use these)

### Install dependencies
Run from repo root:

    python -m pip install -U pip
    pip install -r requirements.txt

If `requirements-dev.txt` exists (recommended), also run:

    pip install -r requirements-dev.txt

### Lint / format
Preferred (if Ruff is configured):

    ruff format .
    ruff check .

### Tests

    pytest

If tests do not exist yet, create at least a **smoke test** that checks `/health` returns `{"status":"ok"}` using `fastapi.testclient.TestClient`.

---

## 2) Definition of done (for every code change)

A change is complete only if ALL apply:

1. The server still starts:

       uvicorn app.main:app --host 0.0.0.0 --port 9700

2. Lint/format passes (Ruff preferred).
3. Tests pass locally (no network required).
4. Any behavior change includes updated/added tests.
5. No secrets are added to code or committed files.

---

## 3) Repository conventions

### App entrypoint
- FastAPI app must be available at: `app.main:app`
- Keep a health endpoint:
  - `GET /health` → `{"status": "ok"}`

### MCP endpoints
- Keep MCP routes under `/mcp/*`.
- When adding new tools, keep request/response JSON stable and document them in README if public-facing.

### Logging
- Use structured, minimal logs.
- Never log full SQL payloads in INFO; if needed, log **hash/length** or redact.

### Type hints
- Prefer type hints and Pydantic models for request/response payloads.
- Avoid overly dynamic dict blobs when the schema is known.

---

## 4) Dependency policy

- Runtime dependencies go to `requirements.txt`.
- Dev-only dependencies go to `requirements-dev.txt` (recommended).
- Do not add new dependencies unless necessary; explain briefly in the PR/commit message.
- Avoid heavy frameworks unless justified.

Recommended dev dependencies (if not present yet):
- `ruff`, `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `mypy`

---

## 5) Testing policy

- Tests must be fast and deterministic.
- Tests must not call external services.
- If code needs LLM output, inject a provider and mock it in tests.
- Prefer unit tests for analyzers and a small number of integration tests for HTTP endpoints.

Suggested minimum tests:
- `tests/test_health.py` for `/health`
- `tests/test_mcp_analyze_smoke.py` for a basic `/mcp/analyze` call (if implemented)

---

## 6) RAG / FAISS guidance

- Store vector index path under an environment variable (e.g. `FAISS_PATH`) and default safely.
- Code must handle “index missing” gracefully (create, or return a clear error).
- Do not embed large binary indices into git.

---

## 7) Security & secrets

- Never commit `.env` with real values.
- Never print or echo environment secrets.
- If any sample config is needed, create `.env.example` with placeholders only.

---

## 8) If something fails

When a command fails:
1. Show the exact error (summarize, do not paste huge logs).
2. Fix root cause with the smallest change.
3. Re-run lint/tests and confirm they pass.

If a tool/config is missing (e.g., Ruff not installed), prefer adding:
- `requirements-dev.txt`
- `pyproject.toml` config
- minimal CI-friendly defaults

But keep changes minimal and explain why.

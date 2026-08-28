# DEPENDENCIES

**Purpose**: exact direct dependencies this project declares — project, package, and
version. **Content**: direct runtime and dev dependencies only, plus notable
runtime-only or transitive exceptions worth flagging. **Style**: terse tables, one row
per package. **Not here**: what a framework is used for architecturally — see
[ARCHITECTURE.md](./ARCHITECTURE.md); technology categories — see
[TECHSTACK.md](./TECHSTACK.md).

## Direct Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pyyaml | ≥6 | YAML parsing for test cases, fixtures, rubrics |
| pydantic | ≥2 | Data validation and schema models (Pydantic v2) |
| python-dotenv | ≥1,<2 | Environment variable loading from .env files |
| ranx | ≥0.3.21,<0.4 | TREC-tested IR ranking metrics for evaluation |
| mcp | ≥1.2 | Model Context Protocol SDK (lazy-imported for MCP transport) |
| fastapi | ≥0.110 | REST API framework for server_rest.py |
| httpx | ≥0.27 | Async HTTP client (REST transport, ASGI in-process support) |

## Direct Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ≥8 | Test runner and assertion library |
| pytest-xdist | ≥3 | Parallel test execution plugin |
| allure-pytest | ==2.13.5 | Allure report integration (pinned to match allure CLI 2.13.8) |

## Transitive Dependencies

Managed by uv via uv.lock. See uv.lock for complete dependency tree with pinned versions and checksums.

## Runtime-Only Dependencies (Not in pyproject.toml)

- **uvicorn**: HTTP server for server_rest.py (imported only in main(), not by test suite)

## Python Version

- **Python 3.12+** (requires-python ≥3.12)

## Notes

- **mcp** is lazy-imported to avoid SDK overhead for in-process evaluation runs
- **ranx** is the only direct dependency for IR metrics (TREC standard)
- **allure-pytest 2.13.5** is pinned due to incompatibility with allure CLI 2.13.8 (v2.16+ breaks JSON format)
- No test/dev dependencies are pinned except allure-pytest (strict versioning per tool.pytest.ini_options: --strict-config)

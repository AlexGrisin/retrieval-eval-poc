# TECHSTACK

**Purpose**: what the workspace runs on — language, package manager, core frameworks,
dev/test tooling, and build entry points. **Content**: detected technologies and their
role, nothing project-specific. **Style**: terse grep-friendly headers, one bullet per
technology. **Not here**: exact versions and licensing detail — see
[DEPENDENCIES.md](./DEPENDENCIES.md); module structure — see
[ARCHITECTURE.md](./ARCHITECTURE.md).

## Runtime Environment

- **Language**: Python 3.12+
- **Package Manager**: uv (lock: uv.lock, non-package project)
- **Package Metadata**: pyproject.toml (PEP 517/518 standard)

## Core Frameworks & Libraries

### Data & Configuration
- **pyyaml** ≥6: YAML parsing for test cases, fixtures, rubrics
- **pydantic** ≥2: Data validation and schema models
- **python-dotenv** ≥1,<2: Environment variable loading (.env file support)

### Retrieval & Ranking
- **ranx** ≥0.3.21,<0.4: TREC-tested IR ranking metrics (evaluation foundation)

### Agent & Service Communication
- **mcp** ≥1.2: Model Context Protocol SDK (lazy-imported, MCP transport boundary)
- **fastapi** ≥0.110: REST API framework (server_rest.py)
- **httpx** ≥0.27: Async HTTP client (REST transport, ASGI in-process support)

## Development & Testing

### Testing Framework
- **pytest** ≥8: Test runner and assertion library
- **pytest-xdist** ≥3: Parallel test execution
- **allure-pytest** ==2.13.5: Test reporting (Allure framework integration)

### Code Quality & Linting
- **ruff**: Code formatter and linter (configured in pyproject.toml)

## Architecture Patterns

### Evaluation Engine
- Modular harness architecture: case execution → validation → ranking → judge
- MCP and REST transport options (lazy imports to avoid SDK bloat)
- Schema-driven contract validation (pydantic models in harness/validators/)

### Test Fixtures & Baselines
- Frozen YAML corpus (fixtures/corpus.yaml)
- Baseline JSON scorecards (baselines/*.json) for regression testing
- Rubric definitions (rubrics/*.yaml) for judge evaluation criteria

### Entry Points
- **probe.py**: CLI entry point for ad-hoc evaluation
- **server_mcp.py**: MCP transport server
- **server_rest.py**: REST API server (uses uvicorn at runtime, not in dependencies)

## Build & Execution

- **uv run**: Execute scripts with environment isolation
- **pytest**: Test discovery and execution from tests/ directory
- **allure**: Report generation from test results
- No CI/CD: Local dev environment only (no .github/ workflows)

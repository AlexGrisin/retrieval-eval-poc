# PATTERNS INDEX

Recurring structural conventions extracted from the codebase (Rosetta Phase 5,
install mode — no prior docs/PATTERNS existed). Each pattern below was verified
by reading the actual code in 2+ places before being included; see each
pattern file for exact file/function evidence. Scope: harness/, skill/,
server_mcp.py, server_rest.py, cases/, rubrics/, fixtures/, tests/. Excluded as
Rosetta-managed / not a pattern source: docs/.

## Strict Boundary Contract (Pydantic v2) - every cross-boundary payload is a single shared `extra="forbid", strict=True` pydantic model with non-blank field validators, defined once and imported by every consumer

See [strict-boundary-contract.md](./strict-boundary-contract.md).

## Deterministic Validator Function - every zero-tolerance check is a pure `check_<requirement>(...) -> str | None` function: `None` means pass, a string means fail, never a boolean or an exception

See [deterministic-validator-function.md](./deterministic-validator-function.md).

## Traceability Registry + record/skip Idiom - a name-keyed registry records where every check's requirement comes from; an unregistered check name is itself treated as an invariant failure rather than a silent pass

See [traceability-registry.md](./traceability-registry.md).

## Multi-Transport Adapter over One Shared Contract - inprocess/mcp/rest clients and server adapters all translate the same domain contract and pydantic wire schema through one shared parsing/marshaling function per direction

See [multi-transport-adapter.md](./multi-transport-adapter.md).

## Lazy Optional-Dependency Import - heavy or transport-specific SDKs (mcp, ranx, httpx, uvicorn) are imported inside the function that needs them, never at module top level

See [lazy-optional-dependency-import.md](./lazy-optional-dependency-import.md).

## YAML Fixture Load-and-Validate at the Boundary - every authored YAML input is parsed and validated exactly once behind a `load_<thing>`/`load_<things>` pair, raising an artifact-named error subclass that names the offending file

See [fixture-load-and-validate.md](./fixture-load-and-validate.md).

## Self-Documenting Inventory Renderer - a registry-backed module exposes `render_inventory(markdown=False)` to print its own contents as plain text or a markdown table without executing anything

See [self-documenting-inventory.md](./self-documenting-inventory.md).

## Content-Hash Fingerprint for Cache Keys and Compatibility Gates - deterministic SHA-256 over canonical file bytes or canonical JSON is the one mechanism for both cache keys and compatibility fingerprints, one hash per independent concern

See [content-hash-fingerprint.md](./content-hash-fingerprint.md).

## Versioned Compatibility Manifest + Regression Gate - a schema-versioned manifest separates environment/target-independent facts, per-result-family profiles, and an explicit allow-list of which target fields may legitimately change, before any metric delta is ever computed

See [versioned-compatibility-manifest.md](./versioned-compatibility-manifest.md).

## Three-State Check Result with Mutual-Exclusion Validation - every check or judged outcome is ok/fail/skip or scored/not_run, never a bare boolean, with skip/not_run always carrying an explicit reason and a validator enforcing the pairing

See [three-state-check-result.md](./three-state-check-result.md).

## Lazy Cached View Chain over Shared Execution - layered view classes each cache their own `__getitem__` lookups over one shared, expensive per-case execution so independent consumers never re-run a case

See [lazy-cached-execution-view.md](./lazy-cached-execution-view.md).

## Pytest Case-Check Marker & Traceability-Driven Test Generation - tests are generated only for applicable (case, check) pairs and carry case/level and traceability markers derived from the same registry the CLI runner uses

See [pytest-case-check-marker.md](./pytest-case-check-marker.md).

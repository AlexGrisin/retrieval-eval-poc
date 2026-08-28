# Lazy Optional-Dependency Import

## Description

Heavy or transport-specific SDKs are imported inside the function or
method that actually needs them, never at module top level — so importing
the module (and running the default fast in-process suite) never pays
their import cost and never requires them to be installed at all.

**Evidence (read directly):**
- `skill/client.py` — `MCPKnowledgeClient._call` imports `mcp.client.client.Client`; `RESTKnowledgeClient._call` imports `httpx`
- `harness/validators/contract.py` — `check_server_rejects_invalid_request` imports `mcp.client.client.Client` in its `mcp` branch and `httpx` in its `rest` branch
- `harness/ranking_metrics.py` — `_ranx_api()` imports `ranx` (and sets cache-directory env vars first, since importing `ranx` pulls in `ir_datasets` and `matplotlib`, neither used directly)
- `harness/runner.py` — `make_skill()` imports `server_mcp.build_server` / `server_rest.build_app` only inside the branch matching the selected `--transport`
- `server_rest.py` — `main()` imports `uvicorn` only when actually serving (it is a runtime-only dependency, not in `pyproject.toml` — see `docs/DEPENDENCIES.md`)

## Template / Example

```python
def uses_an_optional_sdk(...) -> ...:
    """Import the optional SDK here, not at module top level.

    Keeps the default (fast, in-process) path free of an import that only
    this transport/feature needs, and lets the SDK remain an optional
    dependency for users who never exercise this path.
    """
    # EXTENSION POINT: the import line itself IS the extension point —
    # move it here, never to the top of the file, for any dependency that
    # is not needed by the default/fast path.
    import some_heavy_or_optional_sdk

    return some_heavy_or_optional_sdk.do_the_thing(...)
```

For a dependency whose *import itself* has side effects (creates cache
directories, etc. — as `ranx`'s transitive imports do), set the relevant
environment variables with `os.environ.setdefault(...)` immediately before
the lazy import, exactly as `harness/ranking_metrics.py::_ranx_api()`
does, so a read-only sandbox or CI environment is never surprised by a
write to the user's home directory.

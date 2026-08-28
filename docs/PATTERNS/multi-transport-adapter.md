# Multi-Transport Adapter over One Shared Contract

## Description

The evaluated system supports interchangeable transports
(`inprocess` / `mcp` / `rest`) on both sides of the boundary, and in every
case only the wire-marshaling code differs — the domain contract
(`skill/contracts.py`) and its pydantic mirror (`skill/schemas.py`) are
shared, never redefined per transport.

**Client side** (`skill/client.py`): `FakeKnowledgeServer`,
`MCPKnowledgeClient`, and `RESTKnowledgeClient` all satisfy the same
`KnowledgeClient` Protocol (`retrieve(request) -> RetrieveResponse`).
`SpyClient` wraps any of them to record the tool call actually emitted,
without changing behavior. Both network clients funnel through the single
`_response_from_payload()` function — the only thing that differs between
transports is *how* a dict is obtained from the wire (an MCP
`CallToolResult` vs an `httpx.Response`), never how that dict becomes a
`RetrieveResponse`. One parsing path, so the transports cannot silently
diverge on it.

**Server side** (`server_mcp.py`, `server_rest.py`): both files translate
the same `skill/schemas.py` pydantic wire models (`ScopeIn`, `FiltersIn`,
`RetrieveIn`/`QueryText`, `RetrieveResponseOut`) to/from
`skill/contracts.py` dataclasses, call the same
`FakeKnowledgeServer.retrieve()`, and translate the result back. Neither
file defines its own notion of "a valid request."

Adding a new transport means: one new client class (or `build_<transport>`
server function) that reuses the existing schemas/contracts and funnels
through the existing parsing function — never a second, transport-specific
parsing or validation path.

## Template / Example

```python
# skill/client.py — new client, same Protocol, same parsing funnel
class GRPCKnowledgeClient:
    def __init__(self, target: Any) -> None:
        self._target = target

    def retrieve(self, request: RetrieveRequest) -> RetrieveResponse:
        # EXTENSION POINT: only this method knows about the transport SDK,
        # and it is imported lazily inside here (see
        # lazy-optional-dependency-import.md).
        payload = self._call_over_grpc(request.as_tool_call()["args"])
        # EXTENSION POINT: reuse the ONE payload -> RetrieveResponse funnel;
        # never hand-roll a second parser per transport.
        return _response_from_payload(payload)
```

```python
# server_<transport>.py — new server adapter, same schemas/contracts
def build_server(corpus: str | Path = DEFAULT_CORPUS):
    backend = FakeKnowledgeServer(corpus)

    def knowledge_retrieve(query: QueryText, scope: ScopeIn,
                            filters: FiltersIn | None = None,
                            k: int = 10, format: str = "full") -> RetrieveResponseOut:
        # EXTENSION POINT: wire model -> domain dataclass, always this shape
        request = RetrieveRequest(
            query=query,
            scope=Scope(department=scope.department, product=scope.product),
            filters=Filters(
                domain=filters.domain if filters else None,
                veracity=filters.veracity if filters else None,
                validity=filters.validity if filters else "current",
                memory_type=filters.memory_type if filters else None,
            ),
            k=k, format=format,
        )
        # EXTENSION POINT: domain dataclass -> wire model, always this shape
        return RetrieveResponseOut(**backend.retrieve(request).as_dict())
```

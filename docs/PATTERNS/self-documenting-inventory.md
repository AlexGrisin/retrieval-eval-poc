# Self-Documenting Inventory Renderer

## Description

A registry-backed module exposes a `render_inventory(markdown: bool = False)
-> str` function that renders its own registered contents as either a
human-readable plain listing or a markdown table — without executing any
part of the system it describes (no case is run, no model is called).

Implemented independently, twice, with the same signature and the same
markdown/plain switch:
- `harness/validators/registry.py::render_inventory()` renders `CHECKS`
  (name, declared-by, traceability, source, rationale)
- `harness/judges/loader.py::render_inventory()` renders the loaded
  rubrics (name, type, threshold, description, traceability)

Both are surfaced to the CLI: `python3 -m harness.runner --list-checks
[--markdown]` prints the validator inventory and exits without running any
case; `harness/judges/loader.py` is also runnable standalone
(`if __name__ == "__main__": print(render_inventory())`).

## Template / Example

```python
def render_inventory(markdown: bool = False) -> str:
    """Render this module's registry without executing anything it describes."""
    entries = sorted(MY_REGISTRY.items())  # EXTENSION POINT: registry to render

    if markdown:
        # EXTENSION POINT: markdown table columns mirror the plain-text fields
        out = ["| Name | Field A | Field B |", "| --- | --- | --- |"]
        out += [f"| `{name}` | {meta['a']} | {meta['b']} |" for name, meta in entries]
        return "\n".join(out)

    out = [f"{len(entries)} entries.\n"]
    for name, meta in entries:
        out.append(name)
        out.append(f"    field a : {meta['a']}")
        out.append(f"    field b : {meta['b']}")
        out.append("")
    return "\n".join(out)
```

A new registry-like inventory (e.g. a future prompts or transports
registry) should offer this same `render_inventory()` shape rather than a
bespoke printer, and should be wired into `harness/runner.py`'s argument
parser the same way `--list-checks` is, if it needs CLI exposure.

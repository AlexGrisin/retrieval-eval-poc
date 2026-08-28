# Content-Hash Fingerprint for Cache Keys and Compatibility Gates

## Description

Deterministic SHA-256 hashing over canonically-serialized content is the
one mechanism used both to build cache keys and to build compatibility
fingerprints — never an ad hoc version string or a mutable counter.

`harness/baselines.py::hash_paths(root, *paths)` hashes each file's
repo-relative identity plus its bytes (so a rename changes the fingerprint,
not just content edits), and is called **repeatedly with different path
sets** to build independent, separately-named hashes per concern:
`corpus_hash`, `case_set_hash`, `contracts_hash`, `orchestration_hash`,
`validator_hash`, `ranking_hash`, `dependency_lock_hash`,
`retrieval_skill_version`, `knowledge_server_version`. One hash per
concern, not one hash for everything — so when a baseline comparison is
refused, the diagnostic names exactly which concern changed (e.g.
`contracts_hash` differs but `orchestration_hash` doesn't) instead of a
single opaque "something changed."

`harness/judges/prompt.py::canonical_hash(value)` (JSON-dump with
`sort_keys=True` + SHA-256) is the same idea applied to JSON-shaped data
rather than files, and is composed the same way in
`harness/judges/runner.py::_score_input()`'s `cache_key` — built from
`model / model_version / prompt_version / temperature / prompt_hash /
rubric_hash / input_hash / result_schema_version`, each hashed
independently, then hashed together.

## Template / Example

```python
import hashlib
import json
from pathlib import Path


def hash_paths(root: Path, *paths: Path) -> str:
    """Hash both relative identity and content so a rename is a version change."""
    digest = hashlib.sha256()
    for path in sorted(_expand_to_files(paths)):
        identity = path.resolve().relative_to(root.resolve()).as_posix()
        digest.update(identity.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def canonical_hash(value) -> str:
    """Hash JSON-shaped data deterministically (sorted keys, stable separators)."""
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


# EXTENSION POINT: a new independent concern gets its OWN named hash call,
# never folded into an existing one — this is what makes a refused
# comparison's diff readable.
my_new_concern_hash = hash_paths(root, root / "my" / "new" / "concern")

# EXTENSION POINT: composing several hashes into one cache/compatibility
# key is itself a canonical_hash() call over a dict of the individual hashes.
cache_key = canonical_hash({
    "concern_a_hash": concern_a_hash,
    "concern_b_hash": concern_b_hash,
    "schema_version": MY_SCHEMA_VERSION,
})
```

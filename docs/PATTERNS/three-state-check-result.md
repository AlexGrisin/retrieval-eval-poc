# Three-State Check Result with Mutual-Exclusion Validation

## Description

Every executed check or judged criterion has exactly **three** possible
outcomes, never a bare boolean:
- `ok` / `fail` / `skip` — the check dicts built by `harness/runner.py`'s
  `record()`/`skip()` closures, and `harness/agent/models.py`'s
  `AgentCheckResult.status: Literal["ok", "fail", "skip"]`
- `scored` / `not_run` — `harness/judges/models.py`'s
  `JudgeOutcome.status: Literal["scored", "not_run"]`

"Skipped" and "not run" always carry an explicit reason string — never a
silently-absent result. Where the outcome is a pydantic model, a
`model_validator(mode="after")` enforces that the status and payload
cannot be mismatched: `JudgeOutcome.status_matches_payload()` requires a
`"scored"` outcome to carry a `record` and *no* `reason`, and a
`"not_run"` outcome to carry a `reason` and *no* `record` — so a caller
can never accidentally construct an outcome that claims to be scored but
has no score, or claims to be skipped but gives no reason.

This distinguishes "this requirement was never applicable / never ran"
from "this requirement ran and passed" from "this requirement ran and
failed." Collapsing `skip` into `fail` (or into silence) would hide
reduced coverage caused by a case-file typo or a genuinely inapplicable
expectation, which is exactly the failure mode `traceability-registry.md`
also guards against for unregistered check names.

## Template / Example

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator


class MyOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    criterion: str
    # EXTENSION POINT: exactly the states that matter — never collapse
    # "did not run" into "failed", and never allow a bare bool.
    status: Literal["scored", "not_run"]
    record: "MyRecord | None" = None
    reason: str | None = None

    @model_validator(mode="after")
    def status_matches_payload(self) -> "MyOutcome":
        # EXTENSION POINT: this pairing is exactly what prevents a caller
        # from constructing a malformed outcome by accident.
        if self.status == "scored" and (self.record is None or self.reason is not None):
            raise ValueError("a scored outcome requires a record and no reason")
        if self.status == "not_run" and (self.record is not None or not self.reason):
            raise ValueError("a not_run outcome requires a reason and no record")
        return self
```

For the plain-dict (non-pydantic) variant used in `harness/runner.py`,
the same three states are produced by two closures (`record()` for
ok/fail, `skip()` for skip) that both always populate `detail`/`reason`
for the non-`ok` cases — see `traceability-registry.md` for the closure
shape.
